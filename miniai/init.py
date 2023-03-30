# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/clean/11_initializing.ipynb.

# %% auto 0
__all__ = ['init_layers', 'act_layers', 'batch_layers', 'clean_ipython_hist', 'clean_tb', 'clean_mem', 'BatchTfmCB',
           'GeneralReLU', 'plot_func', 'init_weights', 'lsuv_stats', 'lsuv_init', 'LSUVInitCB', 'conv', 'get_model']

# %% ../nbs/clean/11_initializing.ipynb 2
import pickle
import gzip
import math
import sys
import gc
import os
import time
import traceback
import shutil
import torch
import matplotlib.pyplot as plt
import numpy as np
from collections.abc import Mapping
from pathlib import Path
from operator import attrgetter, itemgetter
from functools import partial
from copy import copy

from torch import nn
import torchvision.transforms.functional as TF
from torch import nn, tensor, optim
import torch.nn.functional as F
from torch.utils.data import DataLoader, default_collate
from torch.nn import init
from torcheval.metrics import MulticlassAccuracy
from datasets import load_dataset, load_dataset_builder

from .datasets import * 
from .conv import * 
from .learner import * 
from .activations import * 

# %% ../nbs/clean/11_initializing.ipynb 13
def clean_ipython_hist():
    # Code in this function mainly copied from IPython source
    if not 'get_ipython' in globals(): return
    ip = get_ipython()
    user_ns = ip.user_ns
    ip.displayhook.flush()
    pc = ip.displayhook.prompt_count + 1
    for n in range(1, pc): user_ns.pop('_i'+repr(n),None)
    user_ns.update(dict(_i='',_ii='',_iii=''))
    hm = ip.history_manager
    hm.input_hist_parsed[:] = [''] * pc
    hm.input_hist_raw[:] = [''] * pc
    hm._i = hm._ii = hm._iii = hm._i00 =  ''
    
def clean_tb():
    # h/t Piotr Czapla
    if hasattr(sys, 'last_traceback'):
        traceback.clear_frames(sys.last_traceback)
        delattr(sys, 'last_traceback')
    if hasattr(sys, 'last_type'): delattr(sys, 'last_type')
    if hasattr(sys, 'last_value'): delattr(sys, 'last_value')    
    
def clean_mem():
    clean_tb()
    clean_ipython_hist()
    gc.collect()
    torch.cuda.empty_cache()

# %% ../nbs/clean/11_initializing.ipynb 31
init_layers = (
    nn.Conv1d, 
    nn.Conv2d, 
    nn.Conv3d, 
    nn.ConvTranspose1d, 
    nn.ConvTranspose2d, 
    nn.ConvTranspose3d, 
    nn.Linear)

# %% ../nbs/clean/11_initializing.ipynb 40
import fastcore.all as fc

class BatchTfmCB(Callback):
    def __init__(self, tfm, on_train=True, on_val=True): fc.store_attr()
    def before_batch(self, learn: Learner): 
        if (self.on_train and learn.training) or (self.on_val and not learn.training):
            learn.batch = self.tfm(learn.batch)

# %% ../nbs/clean/11_initializing.ipynb 47
class GeneralReLU(nn.Module):
    def __init__(self, leak=None, sub=None, maxv=None):
        super().__init__()
        self.leak, self.sub, self.maxv = leak, sub, maxv
    
    def forward(self, x):
        x = F.leaky_relu(x, self.leak) if self.leak is not None else F.relu(x)
        if self.sub is not None: x-=self.sub
        if self.maxv is not None: x.clamp_max_(self.maxv)
        return x

# %% ../nbs/clean/11_initializing.ipynb 48
def plot_func(f, start=-5, end=5, steps=100):
    x = torch.linspace(start, end, steps)
    plt.plot(x, f(x))
    plt.grid(True, which='both', ls='--')
    plt.axhline(y=0, color='k', linewidth=0.5)
    plt.axvline(x=0, color='k', linewidth=0.5)

# %% ../nbs/clean/11_initializing.ipynb 52
def init_weights(m, leaky=0.):
    if isinstance(m, init_layers): init.kaiming_normal_(m.weight, a=leaky)

# %% ../nbs/clean/11_initializing.ipynb 59
@hook
def lsuv_stats(hook, mod, inp, out):
    acts = to_cpu(out)
    hook.mean = acts.mean()
    hook.std = acts.std()

# %% ../nbs/clean/11_initializing.ipynb 60
def lsuv_init(model, m, m_in, xb, verbose=False):
    lsuv = lsuv_stats(m) # only hook into the selected layers
    with torch.no_grad():  

        while model(xb) is not None and (abs(lsuv.std-1) > 1e-3 or abs(lsuv.mean) > 1e-3):                 
            m_in.bias -= lsuv.mean
            m_in.weight.data /= lsuv.std   
            if verbose:
                print(f"Init: mean {lsuv.mean} std {lsuv.std}")
    lsuv.remove()

# %% ../nbs/clean/11_initializing.ipynb 69
from fastcore.all import risinstance

act_layers = (    
    nn.ReLU,
    nn.ReLU6,
    GeneralReLU,
)

class LSUVInitCB(Callback):
    def __init__(self, 
                 layers=risinstance(init_layers), 
                 acts=risinstance(act_layers),
                 verbose=False):
        self.layer_filter = layers
        self.act_filter = acts
        self.verbose = verbose
        
    def before_fit(self, learn: Learner):
        layers = [o for o in learn.model.modules() if self.layer_filter(o)]
        activations = [o for o in learn.model.modules() if self.act_filter(o)]
        xb, _ = next(iter(learn.dls.train))
        xb = xb.to(device)
        
        for layer, act in zip(layers, activations):
            lsuv_init(learn.model, act, layer, xb, verbose=self.verbose)

            

# %% ../nbs/clean/11_initializing.ipynb 76
batch_layers = (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)

def conv(ni, nf, ks=3, stride=3, act=nn.ReLU, norm=None, bias=None):
    if bias is None: bias = not isinstance(norm, batch_layers)
    layers = [nn.Conv2d(ni, nf, stride=stride, kernel_size=ks, padding=ks//2, bias=bias)]
    if norm: layers.append(norm(nf))
    if act: layers.append(act())
    return nn.Sequential(*layers)

# %% ../nbs/clean/11_initializing.ipynb 77
def get_model(act=nn.ReLU, nfs=None, norm=None):
    if nfs is None: nfs = [1, 8, 16, 32, 64]
    layers = [conv(nfs[i], nfs[i+1], act=act, norm=norm) 
              for i in range(len(nfs)-1)]
    return nn.Sequential(
        *layers, 
        conv(nfs[-1], 10, act=None, norm=False, bias=True),
        nn.Flatten()).to(device)
