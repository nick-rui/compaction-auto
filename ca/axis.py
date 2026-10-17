"""Assistant Axis measurement / capping on Qwen3-32B (bf16, HF). Runs on the GPU box.

Axis + capping config: huggingface.co/datasets/lu-christina/assistant-axis-vectors (qwen-3-32b),
from Lu et al. 2026, "The Assistant Axis" (safety-research/assistant-axis). Projection follows
their `project`: mean residual-stream output of a decoder layer over response tokens, dotted
with the unit-normalized axis (higher = more Assistant-like). Capping follows their
`ActivationSteering._apply_cap` (subtract the excess projection above tau on every position).
"""

import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = os.path.expanduser(os.environ.get("CA_HF_MODEL", "~/models/Qwen3-32B"))
VEC = os.path.expanduser(os.environ.get("CA_AXIS_DIR", "~/axis-vectors/qwen-3-32b"))
TARGET_LAYER = 32
CAP_EXPERIMENT = "layers_46:54-p0.25"  # the paper's recommended Qwen3-32B setting


class _Stop(Exception):
    pass


class Axis:
    def __init__(self, layers=(16, 24, 32, 40, 48)):
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda")
        self.model.eval()
        self.blocks = self.model.model.layers
        ax = torch.load(f"{VEC}/assistant_axis.pt", map_location="cpu", weights_only=True).float()
        self.axis = (ax / ax.norm(dim=-1, keepdim=True)).cuda()
        self.layers = list(layers)
        self.cap_cfg = torch.load(f"{VEC}/capping_config.pt", map_location="cpu", weights_only=True)

    # ---------- formatting ----------
    def prefix_ids(self, messages, **kw):
        s = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                         enable_thinking=False, **kw)
        return self.tok(s, add_special_tokens=False)["input_ids"]

    def response_ids(self, text):
        return self.tok(text + "<|im_end|>", add_special_tokens=False)["input_ids"]

    # ---------- measurement ----------
    @torch.no_grad()
    def project(self, messages, response, tools=None):
        """Mean projection over response tokens at each layer in self.layers."""
        p = self.prefix_ids(messages, **({"tools": tools} if tools else {}))
        r = self.response_ids(response)[:-1] or self.response_ids(" ")[:1]
        ids = torch.tensor([p + r], device="cuda")
        lo, hi = len(p), len(p) + len(r)
        got, hs = {}, []
        top = max(self.layers)

        def mk(i):
            def h(mod, ins, out):
                t = out[0] if isinstance(out, tuple) else out
                got[i] = t[0, lo:hi].float().mean(0)
                if i == top:
                    raise _Stop
            return h

        for i in self.layers:
            hs.append(self.blocks[i].register_forward_hook(mk(i)))
        try:
            self.model(ids, use_cache=False)
        except _Stop:
            pass
        finally:
            for h in hs:
                h.remove()
        return {i: float(got[i] @ self.axis[i]) for i in self.layers}, len(r), len(p)

    # ---------- capping ----------
    def capping(self, experiment=CAP_EXPERIMENT):
        exp = next(e for e in self.cap_cfg["experiments"] if e["id"] == experiment)
        hooks = []
        for iv in exp["interventions"]:
            vd = self.cap_cfg["vectors"][iv["vector"]]
            v = vd["vector"].float().cuda()
            v = (v / v.norm()).to(torch.bfloat16)
            tau = float(iv["cap"])

            def h(mod, ins, out, v=v, tau=tau):
                t = out[0] if isinstance(out, tuple) else out
                proj = torch.einsum("bld,d->bl", t, v)
                t = t - torch.einsum("bl,d->bld", (proj - tau).clamp(min=0.0), v)
                return (t, *out[1:]) if isinstance(out, tuple) else t
            hooks.append((vd["layer"], h))
        return _Hooks(self.blocks, hooks)

    def steering(self, coef, layer=TARGET_LAYER):
        """Add coef * unit axis at `layer` (positive = more Assistant-like)."""
        v = self.axis[layer].to(torch.bfloat16)

        def h(mod, ins, out):
            t = out[0] if isinstance(out, tuple) else out
            t = t + coef * v
            return (t, *out[1:]) if isinstance(out, tuple) else t
        return _Hooks(self.blocks, [(layer, h)])

    @torch.no_grad()
    def generate(self, messages, n=1, max_new_tokens=900, temperature=0.7, top_p=0.8, top_k=20):
        p = self.prefix_ids(messages)
        # keep KV cache within budget: chunk so that batch * seq_len <= ~32k tokens
        per = max(1, 32_000 // (len(p) + max_new_tokens))
        res = []
        while len(res) < n:
            b = min(per, n - len(res))
            ids = torch.tensor([p] * b, device="cuda")
            out = self.model.generate(ids, attention_mask=torch.ones_like(ids), do_sample=True,
                                      temperature=temperature, top_p=top_p, top_k=top_k,
                                      max_new_tokens=max_new_tokens, pad_token_id=self.tok.eos_token_id)
            res += [self.tok.decode(o[len(p):], skip_special_tokens=True).strip() for o in out]
        return res


class _Hooks:
    def __init__(self, blocks, hooks):
        self.blocks, self.hooks, self.handles = blocks, hooks, []

    def __enter__(self):
        self.handles = [self.blocks[i].register_forward_hook(h) for i, h in self.hooks]
        return self

    def __exit__(self, *a):
        for h in self.handles:
            h.remove()
