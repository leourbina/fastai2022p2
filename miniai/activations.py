# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/clean/10_activations.ipynb.

# %% ../nbs/clean/10_activations.ipynb 2
from __future__ import annotations
import math
import random
import torch
import numpy as np
import matplotlib.pyplot as plt
import fastcore.all as fc
from functools import partial

from .datasets import *
from .learner import * 

# %% auto 0
__all__ = ['set_seed', 'Hook', 'hook', 'model_iter', 'Hooks', 'ActivationsHook', 'HooksCB', 'HistogramHook', 'get_hist',
           'get_min', 'ActivationStats']

# %% ../nbs/clean/10_activations.ipynb 5
def set_seed(seed, deterministic=False):
    torch.use_deterministic_algorithms(deterministic)
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

# %% ../nbs/clean/10_activations.ipynb 26
class Hook:
    def __init__(self, m): self.hook = m.register_forward_hook(self)
    def __call__(self, mod, inp, out): pass
    def remove(self): self.hook.remove()
    def __del__(self): self.remove()

# %% ../nbs/clean/10_activations.ipynb 27
def hook(func):
    class HookFunc(Hook):
        def __call__(self, mod, inp, out):
            return func(self, mod, inp, out)
    return HookFunc

# %% ../nbs/clean/10_activations.ipynb 38
def _model_iter(ms, isleaf):
    if len(ms) == 0:
        return 
    m, *rest = ms    
    children = list(m.children())
    if len(children) == 0 or isleaf(m):
        yield m
    else:
        rest = children + rest
    yield from _model_iter(rest, isleaf)

def model_iter(m, isleaf=lambda x: False):
    return _model_iter([m], isleaf)

class Hooks(dict):
    def __init__(self, *ms, **hooks):
        hook_fns = {key: [t for t in (hook(l) for l in ms) if t is not None] 
                          for key, hook in hooks.items()}
        super().__init__(hook_fns) 
        
    def __enter__(self, *args): return self

    def __exit__(self, *args): self.remove()
    def remove(self): 
        for key in self.keys(): 
            for hook in self[key]:
                hook.remove()

    def __del__(self): self.remove()
    def __delitem__(self, key): 
        self[key].remove()
        super().__delitem__(key)

# %% ../nbs/clean/10_activations.ipynb 39
class ActivationsHook(Hook):
    def __init__(self, m): 
        super().__init__(m)
        self.acts = []
        
    def __call__(self, m, inp, out):
        self.acts.append(to_cpu(out))

# %% ../nbs/clean/10_activations.ipynb 43
class HooksCB(Callback):
    def __init__(self, hook, module_filter=fc.noop, on_train=True, on_valid=False, modules=None):
        fc.store_attr()
        super().__init__()
    
    def before_fit(self, learn: Learner):
        if self.modules: modules=self.modules
        else: modules = fc.filter_ex(learn.model.modules(), self.module_filter)
        self.hooks = Hooks(*modules, hook=partial(self.hookfunc, learn))
    
    def hookfunc(self, learn: Learner, *args, **kwargs):
        if (self.on_train and learn.training) or (self.on_valid and not learn.training):
            return self.hook(*args, **kwargs)
            
    def after_fit(self, learn): self.hooks.remove()
    
    def __iter__(self): 
        if len(self.hooks.keys()) == 1:
            return iter(self.hooks[list(self.hooks.keys())[0]])
        return iter(self.hooks.items())
    
    def __len__(self): 
        if len(self.hooks.keys()) == 1:
            return len(self.hooks[list(self.hooks.keys())[0]])
        return len(self.hooks)

# %% ../nbs/clean/10_activations.ipynb 48
class HistogramHook(Hook):
    def __init__(self, m):
        super().__init__(m)
        self.stats = ([], [], [])

    def __call__(self, mod, inp, out): 
        acts = to_cpu(out)
        self.stats[0].append(acts.mean())
        self.stats[1].append(acts.std())
        self.stats[2].append(acts.abs().histc(50, 0, 10))

# %% ../nbs/clean/10_activations.ipynb 50
def get_hist(h): return torch.stack(h.stats[2]).t().float().log1p()

def get_min(h): # Proportion of the smallest 2% activations compared to the rest
    h1 = torch.stack(h.stats[2]).t().float()
    return h1[0]/h1.sum(0)

# %% ../nbs/clean/10_activations.ipynb 55
class ActivationStats(HooksCB):
    def __init__(self, mod_filter=fc.noop):
        super().__init__(HistogramHook, mod_filter)
    
    def color_dim(self, figsize=(11,5)):
        fig, axs = get_grid(len(self), figsize=figsize)
        for ax, h in zip(axs.flat, self):
            show_image(get_hist(h), ax, origin='lower')
            
    def dead_chart(self, figsize=(11,5)):
        fig, axs = get_grid(len(self), figsize=figsize)
        for ax, h in zip(axs.flat, self):
            ax.plot(get_min(h))
            ax.set_ylim(0,1)
            
    def plot_stats(self, figsize=(11,5)):
        fig, axs = plt.subplots(1, 2, figsize=figsize)
        for h in self:
            for i in 0,1:
                axs[i].plot(h.stats[i])
                
        axs[0].set_title('Means')
        axs[1].set_title('Std Devs')
        plt.legend(fc.L.range(self))
        
