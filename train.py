"""
This file is used to train the model. It is based on the original NanoGPT codebase.
"""

import os
import time
import math
import pickle
import pandas as pd
import yaml

from contextlib import nullcontext

import numpy as np
import torch
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.distributed import init_process_group, destroy_process_group
# torch.autograd.set_detect_anomaly(True) # jason

# from model import GPTConfig, GPT
from pe_info.model_nope import GPTConfig as GPTConfigNOPE, GPT as GPTNOPE
from main_utils import *

# -----------------------------------------------------------------------------
# default config values designed to train a gpt2 (124M) on OpenWebText
# I/O
out_dir = 'out'
resume_dir = None
resume_iter = False # if True, resume from saved iter_num, otherwise resume from iter_num 0
eval_interval = 2000
log_interval = 1
eval_iters = 200
eval_only = False # if True, script exits right after the first eval
always_save_checkpoint = True # if True, always save a checkpoint after each eval
init_from = 'scratch' # 'scratch' or 'resume' or 'gpt2*'
# wandb logging
# wandb_entity = 'ssdd'
wandb_entity = 'littledijkstraz'

wandb_log = False # disabled by default
# wandb_project = 'owt'
wandb_project = 'thesis'
wandb_run_name = 'gpt2' # 'run' + str(time.time())
exp_name = 'default_exp_name'
# data
dataset = 'bal'
gradient_accumulation_steps = 1 # used to simulate larger batch sizes
test_batch_size = 128
batch_size = 12 # if gradient_accumulation_steps > 1, this is the micro-batch size
block_size = 1024
train_data_path = 'train.bin'
val_data_path = 'val.bin'
multi_digit = False
num_digit = 5
binary = False
# using two data - data1 = text / data2 = addition
train_both = False # use seperate text/add data for train/val (get_batch uses this to sample from two differernt datasets)
data_ratio = 0.2 # ratio of data_path2 compared with data_path1
train_data_path2 = 'train_addition.bin' # only used when train_both = True
val_data_path2 = 'val_addition.bin'
# evaluation
eval_text = False # if True get perplexity using eval_text_data_path
eval_text_data_path = None # directory to text data (.bin file) - ex. 'data/shakespeare_add_ar_mixed/val_text.bin' 
eval_addition = False # if True compute test accuracy of "a+b="
start = None
eval_addition_ar = False
start_ar = None
eval_other = False # use this to evaluate other operations (ex. train on operator '-' but evaluate on other_operator '+')
start_other = None
other_operator = '+'
eval_addition_train = False
start_train = None
reverse_ab = False
reverse_c = False
zero_pad = False
algo_reason = False
add_space = False
# model
n_layer = 12
n_head = 12
n_embd = 768
dropout = 0.0 # for pretraining 0 is good, for finetuning try 0.1+
bias = False # do we use bias inside LayerNorm and Linear layers?
ckpt_path_name = 'ckpt.pt'
save_final = True
# adamw optimizer
learning_rate = 6e-4 # max learning rate
max_iters = 600000 # total number of training iterations
weight_decay = 1e-1
beta1 = 0.9
beta2 = 0.95
grad_clip = 1.0 # clip gradients at this value, or disable if == 0.0
# learning rate decay settings
decay_lr = True # whether to decay the learning rate
warmup_iters = 2000 # how many steps to warm up for
lr_decay_iters = 600000 # should be ~= max_iters per Chinchilla
min_lr = None # minimum learning rate, should be ~= learning_rate/10 per Chinchilla
# DDP settings
backend = 'nccl' # 'nccl', 'gloo', etc.
# system
device = 'cuda' # examples: 'cpu', 'cuda', 'cuda:0', 'cuda:1' etc., or try 'mps' on macbooks
dtype = 'bfloat16' if torch.cuda.is_bf16_supported() else 'float16' # 'float32', 'bfloat16', or 'float16', the latter will auto implement a GradScaler
compile = True # use PyTorch 2.0 to compile the model to be faster
use_flash = True
data_type = 'binary' # 'binary' by default, can be 'text'
operator = '+' # can be '+', '-', '*', 'sin', 'sqrt'
data_shuffle = True

# data_format = 'plain' # 'plain' or 'reverse' or 'algo_reasoning'
# jason: change this to reverse
data_format = 'reverse'

vocabulary = 'all_ascii_chars' # can be 'all_ascii_chars' or 'numbers_only' or 'custom_input_data'
meta_path_specified = True # use saved meta_file (False if data_type='text')
eps = 0
tokenizer = 'char' # by default, use char level tokenizer. but for pretrained models, use openai tokenizer eg: 'gpt2'

simple=False
random_A=False
random_C=False

use_lora = False # use lora (from minLoRA)
print_interval = 2  # if we're using gpt-2 model, I want to see it prompted on text

# jason's changes

general_seed = 1337
# general_seed = 1227
resume_metric_from_best = True
use_pe = 'original'
use_residual = True
no_att_residual = False
no_mlp_residual = False
layerwise_pe = False
layer_pe = use_pe
permute = False
permute_length = None
not_causal = False



causal_training=True
non_causal_fix_length = None
save_best_loss = True
autoregressive_training = False # a mode that make the model do auto-regressive training on only the answer part of the equation
save_all_intermediate = False # save all intermediate checkpoints


if __name__ == "__main__":
    # -----------------------------------------------------------------------------
    config_keys = [k for k,v in globals().items() if not k.startswith('_') and isinstance(v, (int, float, bool, str, type(None)))]
    exec(open('configurator.py').read()) # overrides from command line or config file
    config = {k: globals()[k] for k in config_keys} # will be useful for logging
    # -----------------------------------------------------------------------------


    # jason's change:
    if 'use_residual' in config.keys():
        print(f"using residual: {config['use_residual']}")
        print(f"using residual: {use_residual}")    
    if 'use_pe' in config.keys():
        print(f"using pe: {config['use_pe']}")
        print(f"using pe: {use_pe}")

    # exit()
    # jason's change:
    pe_status = '' if use_pe=='original' else f'_{use_pe}'
    residual_status = '' if use_residual==True else f'_res={use_residual}'
    no_att_residual_status = '' if no_att_residual==False else f"_a{no_att_residual}" if isinstance(no_att_residual, bool) else f"_a{''.join(map(str, no_att_residual))}" 
    no_mlp_residual_status = '' if no_mlp_residual==False else f"_m{no_mlp_residual}" if isinstance(no_mlp_residual, bool)  else f"_m{''.join(map(str,no_mlp_residual))}"
    layerwise_pe_status = '' if layerwise_pe==False else f"_lwp{layerwise_pe}" if isinstance(layerwise_pe, bool) else f"_lwp{''.join(map(str,layerwise_pe))}"
    permute_status = '' if permute==False else f"_pm{permute}" if isinstance(permute, bool) else f"_pm{''.join(map(str,permute))}"
    not_causal_status = '' if not_causal==False else f"_nc{not_causal}" if isinstance(not_causal, bool) else f"_nc{''.join(map(str,not_causal))}"
    n_layer_status = f"_n{n_layer}" if n_layer!=6 else ''

    combined_subfix = pe_status + residual_status + no_att_residual_status + \
                no_mlp_residual_status + layerwise_pe_status + n_layer_status + permute_status + not_causal_status

    # out_dir = config['out_dir'] = config['out_dir'] + combined_subfix
    # wandb_run_name = config['wandb_run_name'] = config['wandb_run_name'] + combined_subfix

    import datetime
    current_datetime = datetime.datetime.now()
    formatted_datetime = '_T' + current_datetime.strftime("%y%m%d%H%M") 
    out_dir = config['out_dir'] =  out_dir + str(formatted_datetime) + combined_subfix
    wandb_run_name = config['wandb_run_name'] = wandb_run_name + str(formatted_datetime) + combined_subfix



    model_specific_parameters = ['n_layer', 'n_head', 'n_embd', 'block_size', 'bias', 'vocab_size', 'use_residual', 'use_pe', 'no_att_residual', 'no_mlp_residual', 'layerwise_pe', 'permute', 'not_causal']


    if min_lr == None:
        min_lr = learning_rate/10

    # various inits, derived attributes, I/O setup
    ddp = int(os.environ.get('RANK', -1)) != -1 # is this a ddp run?
    print('ddp: ', ddp)
    if ddp:
        init_process_group(backend=backend)
        ddp_rank = int(os.environ['RANK'])
        ddp_local_rank = int(os.environ['LOCAL_RANK'])
        device = f'cuda:{ddp_local_rank}'
        torch.cuda.set_device(device)
        master_process = ddp_rank == 0 # this process will do logging, checkpointing etc.
        seed_offset = ddp_rank # each process gets a different seed
    else:
        # if not ddp, we are running on a single gpu, and one process
        master_process = True
        seed_offset = 0

    if master_process:
        os.makedirs(out_dir, exist_ok=True)
    torch.manual_seed(general_seed + seed_offset)
    torch.backends.cuda.matmul.allow_tf32 = True # allow tf32 on matmul
    torch.backends.cudnn.allow_tf32 = True # allow tf32 on cudnn
    torch.backends.cudnn.benchmark = True # cudnn auto-tuner
    torch.backends.cudnn.deterministic = False # cudnn auto-tuner
    # this is probably overkill but seed everything agian
    set_seed(general_seed + seed_offset)


    device_type = 'cuda' if 'cuda' in device else 'cpu' # for later use in torch.autocast
    # note: float16 data type will automatically use a GradScaler
    ptdtype = {'float32': torch.float32, 'bfloat16': torch.bfloat16, 'float16': torch.float16}[dtype]
    ctx = nullcontext() if device_type == 'cpu' else torch.amp.autocast(device_type=device_type, dtype=ptdtype)

    # poor man's data loader
    if data_type == 'binary':
        data_dir = os.path.join('data', dataset)
        train_data = np.memmap(os.path.join(data_dir, train_data_path), dtype=np.uint16, mode='r')
        val_data = np.memmap(os.path.join(data_dir, val_data_path), dtype=np.uint16, mode='r')
        if train_both:
            train_data2 = np.memmap(os.path.join(data_dir, train_data_path2), dtype=np.uint16, mode='r')
            val_data2 = np.memmap(os.path.join(data_dir, val_data_path2), dtype=np.uint16, mode='r')
        if eval_text:
            if eval_text_data_path is None:
                print('eval_text_data_path is None!!! No binary file to evaluate perplexity on.') 
            eval_text_data = np.memmap(eval_text_data_path, dtype=np.uint16, mode='r')
        # test_data_str = None # test_data for addition testing will be handled with "start"
        meta_path = None
    else:
        # check for data_format
        if data_type == 'text':
            if ('reverse' in data_format and not reverse_c) or (reverse_c and 'reverse' not in data_format):
                raise ValueError('reverse_c must be True for data_format == "reverse"')
            elif (data_format == 'algo_reasoning' and not algo_reason) or (algo_reason and data_format != 'algo_reasoning'):
                raise ValueError('algo_reason must be True for data_format == "algo_reasoning"')
        meta_path_specified = False

        data_dir = os.path.join('data', dataset)
        train_data_path = os.path.join(data_dir, train_data_path)
        # val_data = os.path.join(data_dir, val_data_path)
        train_data_list = get_data_list(train_data_path, operator=operator) # a list of (x, y, op)
        val_data_list = get_data_list(filename=None, operator=operator) # get_data_list(val_data, operator='+')
        train_data_str = generate_data_str(train_data_list, operator=operator, format=data_format, train=True, shuffle=data_shuffle, add_space=add_space, simple=simple, random_A=random_A, random_C=random_C)
        val_data_str = generate_data_str(val_data_list, operator=operator, format=data_format, train=True, shuffle=data_shuffle, add_space=add_space, simple=simple, random_A=random_A, random_C=random_C)
        meta, meta_path, data_encoder, data_decoder = create_meta_file(vocabulary=vocabulary, input_data_str=train_data_str, tokenizer=tokenizer)
        meta_vocab_size = meta['vocab_size']
        train_data = data_encoder(train_data_str)
        val_data = data_encoder(val_data_str)
        if eval_addition_train and start_train is None:
            # specify the start_train to be our train data file
            start_train = f"FILE:{train_data_path}"
            
        if train_both:
            print('training both')
            # This is for the case where we use two different datasets for training
            # we sample from both with a specified ratio - data_ratio
            # TODO: let's leave this here for now.
            train_data2 = np.memmap(os.path.join(data_dir, train_data_path2), dtype=np.uint16, mode='r')
            val_data2 = np.memmap(os.path.join(data_dir, val_data_path2), dtype=np.uint16, mode='r')
        
        if eval_text:
            # eval_text_data = np.memmap(eval_text_data_path, dtype=np.uint16, mode='r')
            text_data_list = get_data_list(eval_text_data_path, operator='text')
            text_data_str = generate_data_str(text_data_list, operator='text', format=data_format, train=False, shuffle=False)
            eval_text_data = data_encoder(text_data_str)

    space_token = data_encoder(' ')[0]
    switch_line_token = data_encoder('\n')[0]
    equal_token = data_encoder('=')[0]
    dollar_token = data_encoder('$')[0]

    # def get_batch(split):
    #     data = train_data if split == 'train' else val_data
    #     if train_both:
    #         data2 = train_data2 if split == 'train' else val_data2
    #         batch_size2 = int(batch_size*data_ratio)
    #         start_points = torch.randint(len(data) - block_size, (batch_size-batch_size2,))
    #         start_points2 = torch.randint(len(data2) - block_size, (batch_size2,))
    #     else:
    #         if causal_training:
    #             start_points = torch.randint(len(data) - block_size, (batch_size,))
    #         else:
    #             split_points = np.where(data==(switch_line_token))[0]
    #             split_points = np.hstack([np.array([0]), split_points.flatten()])

    #             sample_length_list = np.diff(split_points)
    #             start_points = split_points[:-1]

    #             randidx = np.random.permutation(len(start_points))[:batch_size]
    #             start_points = start_points[randidx]
    #             sample_length_list = sample_length_list[randidx]

    #     if causal_training:
    #         x = torch.stack([torch.from_numpy((data[i:i+block_size]).astype(np.int64)) for i in start_points])
    #         y = torch.stack([torch.from_numpy((data[i+1:i+1+block_size]).astype(np.int64)) for i in start_points])
    #     else:
    #         x = torch.stack([torch.from_numpy(np.pad(data[start_points[i]:start_points[i]+sample_length_list[i]-1].astype(np.int64), 
    #                                         (non_causal_fstart_points_length-sample_length_list[i], 0),  # this pads space at front
    #                                         mode='constant', 
    #                                         constant_values=space_token)) for i in range(len(start_points))])
    #         y = torch.stack([torch.from_numpy((data[start_points[i]+sample_length_list[i]-1:start_points[i]+1+sample_length_list[i]-1]).astype(np.int64)) for i in range(len(start_points))])

    #     if train_both:
    #         x2 = torch.stack([torch.from_numpy((data2[i:i+block_size]).astype(np.int64)) for i in start_points2])
    #         y2 = torch.stack([torch.from_numpy((data2[i+1:i+1+block_size]).astype(np.int64)) for i in start_points2])
    #         x = torch.cat([x,x2])
    #         y = torch.cat([y,y2])    

    #     if device_type == 'cuda':
    #         # pin arrays x,y, which allows us to move them to GPU asynchronously (non_blocking=True)
    #         x, y = x.pin_memory().to(device, non_blocking=True), y.pin_memory().to(device, non_blocking=True)
    #     else:
    #         x, y = x.to(device), y.to(device)
    #     return x, y


    def get_batch(split):
        attn_mask = None
        w = None
        data = train_data if split == 'train' else val_data
        if train_both:
            data2 = train_data2 if split == 'train' else val_data2
            batch_size2 = int(batch_size*data_ratio)
            ix = torch.randint(len(data) - block_size, (batch_size-batch_size2,))
            ix2 = torch.randint(len(data2) - block_size, (batch_size2,))
        else:
            if causal_training:
                ix = torch.randint(len(data) - block_size, (batch_size,))
            else:
                split_points = np.where(data==(switch_line_token))[0]
                answer_split_points = np.where(data==(equal_token))[0]
                answer_length_list = split_points - answer_split_points - 1
                split_points = split_points + 1 # i should have had this
                split_points = np.hstack([np.array([0]), split_points.flatten()])

                sample_length_list = np.diff(split_points)
                start_points = split_points[:-1]

                randidx = np.random.permutation(len(start_points))[:batch_size]
                ix = start_points[randidx]
                sample_length_list = sample_length_list[randidx]
                answer_length_list = answer_length_list[randidx]

        if causal_training:
            x = torch.stack([torch.from_numpy((data[i:i+block_size]).astype(np.int64)) for i in ix])
            y = torch.stack([torch.from_numpy((data[i+1:i+1+block_size]).astype(np.int64)) for i in ix])
        else:
            remove_dollar_count = 1 if dollar_token in data else 0
            if not autoregressive_training:
                cur_answer_length_list = np.random.randint(1+remove_dollar_count, answer_length_list+1) + 1
            else:
                cur_answer_length_list = answer_length_list + 1 + 4
            x = [data[ix[i]:ix[i]+sample_length_list[i]-cur_answer_length_list[i]].astype(np.int64) for i in range(len(ix))]
            x_len = [len(x[i]) for i in range(len(x))]
            pad_to_length = max(x_len)
            min_length = min(x_len)
            # only do padding when the length is not equal
            if pad_to_length > min_length: 
                x = np.vstack([np.pad(x[i], (pad_to_length-len(x[i]), 0), mode='constant', constant_values=space_token) for i in range(len(x))])
                attn_mask = np.ones_like(x)
                # mask out the paddings
                attn_mask[x==space_token] = 0
                attn_mask = attn_mask[..., None]
                attn_mask = attn_mask @ attn_mask.transpose(0, 2, 1)
                attn_mask = attn_mask.astype(bool)
                if (attn_mask==1).all():
                    attn_mask = None
                else:
                    attn_mask = torch.from_numpy(attn_mask)
            else:
                x = np.vstack(x)
                attn_mask = None
            
            x = torch.from_numpy(x)
            # predict the next digit
            if not autoregressive_training:
                y = torch.stack([torch.from_numpy((data[ix[i]+sample_length_list[i]-cur_answer_length_list[i]:ix[i]+1+sample_length_list[i]-cur_answer_length_list[i]]).astype(np.int64)) for i in range(len(ix))])
            else:
                y = [torch.from_numpy((data[ix[i]+sample_length_list[i]-cur_answer_length_list[i]:ix[i]-1+sample_length_list[i]]).astype(np.int64)) for i in range(len(ix))]
                max_len_y = max([len(y[i]) for i in range(len(y))])
                y = np.vstack([np.pad(y[i], (0, max_len_y-len(y[i])), mode='constant', constant_values=space_token) for i in range(len(y))])
                y = torch.from_numpy(y)
                w = torch.ones_like(y)
                w[y==space_token] = 0

        if train_both:
            x2 = torch.stack([torch.from_numpy((data2[i:i+block_size]).astype(np.int64)) for i in ix2])
            y2 = torch.stack([torch.from_numpy((data2[i+1:i+1+block_size]).astype(np.int64)) for i in ix2])
            x = torch.cat([x,x2])
            y = torch.cat([y,y2])    

        if device_type == 'cuda':
            # pin arrays x,y, which allows us to move them to GPU asynchronously (non_blocking=True)
            x, y = x.pin_memory().to(device, non_blocking=True), y.pin_memory().to(device, non_blocking=True)
            if autoregressive_training:
                w = w.pin_memory().to(device, non_blocking=True)    
            if attn_mask is not None:
                attn_mask = attn_mask.pin_memory().to(device, non_blocking=True)
        else:
            x, y = x.to(device), y.to(device)
            
            if attn_mask is not None:
                attn_mask = attn_mask.to(device)
        
        # attn_mask = None
        return x, y, attn_mask, w



    # init these up here, can override if init_from='resume' (i.e. from a checkpoint)
    iter_num = 0
    best_val_loss = 1e9
    best_perplexity = 1e9 # on text data
    best_accuracy = -1 # on addition data

    if meta_path_specified:
        # attempt to derive vocab_size from the dataset
        meta_path = os.path.join(data_dir, 'meta.pkl')
        meta_vocab_size = None
        if os.path.exists(meta_path):
            with open(meta_path, 'rb') as f:
                meta = pickle.load(f)
            meta_vocab_size = meta['vocab_size']
            print(f"found vocab_size = {meta_vocab_size} (inside {meta_path})")
        else:
            meta_path = None

    # model init
    model_args = dict(n_layer=n_layer, n_head=n_head, n_embd=n_embd, block_size=block_size,
                    bias=bias, vocab_size=None, dropout=dropout, use_flash=use_flash,
                    use_residual=use_residual, use_pe=use_pe, 
                    no_att_residual=no_att_residual, 
                    no_mlp_residual=no_mlp_residual,
                    layerwise_pe=layerwise_pe,
                    layer_pe=layer_pe,
                    permute=permute,
                    permute_length=permute_length,
                    not_causal=not_causal
                ) # jason's change 

    # start with model_args from command line
    if init_from == 'scratch':
        # init a new model from scratch
        print("Initializing a new model from scratch")
        # determine the vocab size we'll use for from-scratch training
        if meta_vocab_size is None:
            print("defaulting to vocab_size of GPT-2 to 50304 (50257 rounded up for efficiency)")
        model_args['vocab_size'] = meta_vocab_size if meta_vocab_size is not None else 50304
        # if use_pe=='original':
        #     gptconf = GPTConfig(**model_args)
        #     model = GPT(gptconf)
        # elif use_pe == 'nope':
        gptconf = GPTConfigNOPE(**model_args)
        model = GPTNOPE(gptconf)
    elif init_from == 'resume':
        if resume_dir:
            checkpoint = torch.load(resume_dir, map_location=device)
        else:
            print(f"Resuming training from {out_dir}")
            # resume training from a checkpoint.
            ckpt_path = os.path.join(out_dir, ckpt_path_name)
            checkpoint = torch.load(ckpt_path, map_location=device)
        checkpoint_model_args = checkpoint['model_args']
        # force these config attributes to be equal otherwise we can't even resume training
        # the rest of the attributes (e.g. dropout) can stay as desired from command line
        for k in model_specific_parameters: # jason's change
            model_args[k] = checkpoint_model_args[k]
        # create the model
        # if use_pe=='original':
        #     gptconf = GPTConfig(**model_args)
        #     model = GPT(gptconf)
        # elif use_pe == 'nope':
        gptconf = GPTConfigNOPE(**model_args)
        model = GPTNOPE(gptconf)
        state_dict = checkpoint['model']
        # fix the keys of the state dictionary :(
        # honestly no idea how checkpoints sometimes get this prefix, have to debug more
        unwanted_prefix = '_orig_mod.'
        for k,v in list(state_dict.items()):
            if k.startswith(unwanted_prefix):
                state_dict[k[len(unwanted_prefix):]] = state_dict.pop(k)
        model.load_state_dict(state_dict)
        iter_num = checkpoint['iter_num'] if resume_iter else 0
        max_iters += iter_num
    
        if resume_metric_from_best:
            best_val_loss = checkpoint['best_val_loss']
            if 'best_perplexity' in checkpoint.keys(): 
                best_perplexity = checkpoint['best_perplexity']
            if 'best_accuracy' in checkpoint.keys():
                best_accuracy = checkpoint['best_accuracy']
        else:
            best_val_loss = 1e9
            best_perplexity = 1e9
            best_accuracy = -1
    elif init_from.startswith('gpt2'):
        print(f"Initializing from OpenAI GPT-2 weights: {init_from}")
        # initialize from OpenAI GPT-2 weights
        override_args = dict(dropout=dropout)
        
        # if use_pe=='original':
            # model = GPT.from_pretrained(init_from, override_args)
        # elif use_pe == 'nope':
        model = GPTNOPE.from_pretrained(init_from, override_args)
        # read off the created config params, so we can store them into checkpoint correctly
        for k in model_specific_parameters: # jason's change
            model_args[k] = getattr(model.config, k)
    # crop down the model block size if desired, using model surgery
    if block_size < model.config.block_size:
        model.crop_block_size(block_size)
        model_args['block_size'] = block_size # so that the checkpoint will have the right value
    if use_lora:
        import minlora
        import inspect
        minlora.add_lora(model, lora_config=lora_config)
        minlora.tie_weights(linear=model.lm_head, embedding=model.transformer.wte)
        # optimizer
        def configure_optimizers_lora(self, weight_decay, learning_rate, betas, device_type):
            # we apply weight decay to all lora params
            optim_groups = [
                # note: .get_lora_params() returns a generator
                # we need to wrap it in a list so we can consume it twice
                {"params": list(minlora.get_lora_params(self)) , "weight_decay": weight_decay},
                # you can also add biases for fine-tuning,
                # but I want to make sure lora alone works
                # {"params": minlora.get_bias_params(self), "weight_decay": 0.0}, # bias params don't get weight decay
            ]

            def parameter_count(optim_groups):
                n = sum(p.numel() for group in optim_groups for p in group["params"])
                if n < 1e6:
                    return f"{n/1e3:.1f}k"
                else:
                    return f"{n/1e6:.1f}M"

            print(f"optimizing {parameter_count(optim_groups)} parameters")

            # new PyTorch nightly has a new 'fused' option for AdamW that is much faster
            use_fused = (device_type == "cuda") and ("fused" in inspect.signature(torch.optim.AdamW).parameters)
            print(f"using fused AdamW: {use_fused}")
            extra_args = dict(fused=True) if use_fused else dict()
            optimizer = torch.optim.AdamW(optim_groups, lr=learning_rate, betas=betas, **extra_args)

            return optimizer

    model.to(device)

    # initialize a GradScaler. If enabled=False scaler is a no-op
    scaler = torch.cuda.amp.GradScaler(enabled=(dtype == 'float16'))

    # optimizer
    if use_lora:
        optimizer = configure_optimizers_lora(model, weight_decay, learning_rate, (beta1, beta2), device_type)
    else:
        optimizer = model.configure_optimizers(weight_decay, learning_rate, (beta1, beta2), device_type)
    if init_from == 'resume' and not use_lora:
        optimizer.load_state_dict(checkpoint['optimizer'])

    # compile the model
    if compile:
        print("compiling the model... (takes a ~minute)")
        unoptimized_model = model
        model = torch.compile(model) # requires PyTorch 2.0

    # wrap model into DDP container
    if ddp:
        model = DDP(model, device_ids=[ddp_local_rank])

    # helps estimate an arbitrarily accurate loss over either split using many batches
    @torch.no_grad()
    def estimate_loss():  # this function sometimes get things wrong
        out = {}
        model.eval()
        for split in ['train', 'val']:
            losses = torch.zeros(eval_iters)
            for k in range(eval_iters):
                X, Y, M, W = get_batch(split)
                with ctx:
                    if not autoregressive_training:
                        logits, loss = model(X, Y, causal_training=causal_training, attn_mask=M)
                    else:
                        logits, loss = model.autoregressive_training(X, Y, W, max_new_tokens=Y.shape[-1], attn_mask=M)
                losses[k] = loss.item()
            out[split] = losses.mean()
        model.train()
        return out

    # learning rate decay scheduler (cosine with warmup)
    def get_lr(it):
        # 1) linear warmup for warmup_iters steps
        if it < warmup_iters:
            return learning_rate * it / warmup_iters
        # 2) if it > lr_decay_iters, return min learning rate
        if it > lr_decay_iters:
            return min_lr
        # 3) in between, use cosine decay down to min learning rate
        decay_ratio = (it - warmup_iters) / (lr_decay_iters - warmup_iters)
        assert 0 <= decay_ratio <= 1
        coeff = 0.5 * (1.0 + math.cos(math.pi * decay_ratio)) # coeff ranges 0..1
        return min_lr + coeff * (learning_rate - min_lr)

    # logging
    if wandb_log and master_process:
        import wandb
        wandb.init(project=wandb_project, entity=wandb_entity, name=wandb_run_name, config=config)

    # training loop
    X, Y, M, W = get_batch('train') # fetch the very first batch
    t0 = time.time()
    local_iter_num = 0 # number of iterations in the lifetime of this process
    raw_model = model.module if ddp else model # unwrap DDP container if needed
    running_mfu = -1.0

    # TODO: we already have data_encoder and data_decoder here. Shouldn't need to call this again.
    encode, decode = get_encode_decode(meta_path, tokenizer=tokenizer)
    if 'gpt2' in init_from:
        print("Prompting model before starting the whole process.")
        print_model_output(model, encode, decode, device=device)
        if add_space:
            print_model_output(model, encode, decode, device=device, max_new_tokens=5, start='4 2 + 7 9 =')
        else: 
            print_model_output(model, encode, decode, device=device, max_new_tokens=3, start='$42+79=')

    result_dict = {'iter': [], 'train_loss': [], 'val_loss': [], 'val_ppl': [], 'test_acc': [], 'train_acc': [], 'test_acc_ar': [], 'test_acc_other': []}
    if multi_digit:
        digit_accuracy_dictionary = {}
        for digit in range(1, num_digit+1):
            digit_accuracy_dictionary[f"digit_{digit}"] = []

    result_dir = get_results_dir(config)
    config['result_dir'] = result_dir
    if 'OP_NO_RENEGOTIATION' in config:
        del config['OP_NO_RENEGOTIATION']
    with open(os.path.join(result_dir, "config.yaml"), "w") as yaml_file:
        yaml.dump(config, yaml_file, default_flow_style=False)

    while True:
        # determine and set the learning rate for this iteration
        lr = get_lr(iter_num) if decay_lr else learning_rate
        for param_group in optimizer.param_groups:
            param_group['lr'] = lr

        # evaluate the loss on train/val sets and write checkpoints
        if iter_num % eval_interval == 0 and master_process:
            # losses = estimate_loss() # jason: this line seem to have some issue with global variables?

            losses = {}
            model.eval()
            with torch.no_grad():
                for split in ['train', 'val']:
                    all_loss = torch.zeros(eval_iters)
                    for k in range(eval_iters):
                        X, Y, M, W = get_batch(split)
                        with ctx:
                            if not autoregressive_training:
                                logits, loss = model(X, Y, causal_training=causal_training, attn_mask=M)
                            else:
                                logits, loss = model.autoregressive_training(X, Y, W, max_new_tokens=Y.shape[-1], attn_mask=M)
                        all_loss[k] = loss.item()
                    losses[split] = all_loss.mean().detach().cpu().numpy()
            model.train()

            if eval_text:
                ppl = evaluate_text(config, model, eval_text_data, ctx)
                print(f"perplexity of evluation text data: {ppl}")
            if eval_addition:
                if multi_digit:
                    # digit_accuracy_dictionary = evaluate_addition_multidigit(config, model, ctx, encode, decode, verbose=False, num_digit=num_digit, zero_pad=zero_pad, 
                    #                                                          reverse_ab=reverse_ab, reverse_c=reverse_c, algo_reason=algo_reason, binary=binary)
                    # changing it to use evaluate_addition_batch, we change config['start'] here instead
                    this_dictionary = {}
                    for digit in range(1, num_digit+1):
                        config['start'] = f"FILE:data/multi_digit/test_{digit}digit_100.txt"
                        digit_accuracy, _ = evaluate_addition_batch(config, model, ctx, encode, decode, verbose=True, num_digit=digit, zero_pad=zero_pad, 
                                                        reverse_ab=reverse_ab, reverse_c=reverse_c, algo_reason=algo_reason, 
                                                        binary=binary, data_type=data_type, operator=operator, data_format=data_format)
                        digit_accuracy_dictionary[f"digit_{digit}"].append(digit_accuracy)
                        this_dictionary[f"digit_{digit}"] = digit_accuracy
                config['start'] = start
                test_accuracy, _ = evaluate_addition_batch(config, model, ctx, encode, decode, verbose=True, num_digit=num_digit, zero_pad=zero_pad, 
                                                        reverse_ab=reverse_ab, reverse_c=reverse_c, algo_reason=algo_reason, 
                                                        binary=binary, data_type=data_type, operator=operator, data_format=data_format)
            if eval_addition_ar:
                config['start'] = start_ar
                test_accuracy_ar, _ = evaluate_addition_batch(config, model, ctx, encode, decode, verbose=True, num_digit=num_digit, zero_pad=zero_pad, 
                                                        reverse_ab=reverse_ab, reverse_c=reverse_c, algo_reason=True, 
                                                        binary=binary, data_type=data_type, operator=operator, data_format='algo_reasoning')
            if eval_other:
                config['start'] = start_other
                test_accuracy_other, _ = evaluate_addition_batch(config, model, ctx, encode, decode, verbose=True, num_digit=num_digit, zero_pad=zero_pad, 
                                                        reverse_ab=reverse_ab, reverse_c=reverse_c, algo_reason=algo_reason, 
                                                        binary=binary, data_type=data_type, operator=other_operator, data_format=data_format)

            if eval_addition_train:
                config['start'] = start_train
                train_accuracy, _ = evaluate_addition_batch(config, model, ctx, encode, decode, verbose=False, num_digit=num_digit, zero_pad=zero_pad, 
                                                            reverse_ab=reverse_ab, reverse_c=reverse_c, algo_reason=algo_reason, 
                                                            binary=binary, data_type=data_type, operator=operator, data_format=data_format)
            print(f"step {iter_num}: train loss {losses['train']:.4f}, val loss {losses['val']:.4f}")
            if wandb_log:
                wandb_dict = {
                    "iter": iter_num,
                    "train/loss": losses['train'], # has some problem
                    # 'train/loss': losses['train'].item(),
                    "val/loss": losses['val'],
                    # 'val/loss': losses['val'].item(),
                    "lr": lr,
                    "mfu": running_mfu*100, # convert to percentage,
                    "ppl": ppl if eval_text else None, 
                    "test/accuracy": test_accuracy if eval_addition else None, 
                    "test/accuracy_ar": test_accuracy_ar if eval_addition_ar else None,
                    "test/accuracy_other": test_accuracy_other if eval_other else None,
                    "train/accuracy": train_accuracy if eval_addition_train else None
                }
                if multi_digit:
                    wandb_dict.update(this_dictionary)
                wandb.log(wandb_dict)

            result_dict['iter'].append(iter_num)
            result_dict['train_loss'].append(losses['train'])
            result_dict['val_loss'].append(losses['val'])
            result_dict['val_ppl'].append(ppl.item() if eval_text else None)
            result_dict['test_acc'].append(test_accuracy if eval_addition else None)
            result_dict['train_acc'].append(train_accuracy if eval_addition_train else None)
            result_dict['test_acc_ar'].append(test_accuracy_ar if eval_addition_ar else None)
            result_dict['test_acc_other'].append(test_accuracy_other if eval_other else None)

            if multi_digit:
                result_dict.update(digit_accuracy_dictionary)
            result_df = pd.DataFrame(result_dict)
            result_df.to_csv(os.path.join(result_dir, 'result.csv'), index=False)
            
            checkpoint = {
                        'model': raw_model.state_dict(),
                        'optimizer': optimizer.state_dict(),
                        'model_args': model_args,
                        'iter_num': iter_num,
                        'best_val_loss': best_val_loss,
                        'best_perplexity': best_perplexity,
                        'best_accuracy': best_accuracy,
                        'config': config,
                    }
            if use_lora:
                checkpoint['lora'] = minlora.get_lora_state_dict(raw_model)
            if losses['val'] < best_val_loss or always_save_checkpoint:
                best_val_loss = losses['val']
                checkpoint['best_val_loss'] = best_val_loss
                if save_best_loss:
                    if iter_num > 0:
                        print(f"saving checkpoint to {out_dir}/{ckpt_path_name}")
                        torch.save(checkpoint, os.path.join(out_dir, ckpt_path_name))
            if eval_text and ppl < best_perplexity:
                best_perplexity = ppl
                checkpoint['best_perplexity'] = best_perplexity
                if iter_num > 0:
                    print(f"saving checkpoint to {out_dir}/{ckpt_path_name}")
                    torch.save(checkpoint, os.path.join(out_dir, ckpt_path_name.split('.pt')[0]+'_ppl.pt'))
            if eval_addition and ((test_accuracy > best_accuracy) or save_all_intermediate):
                best_accuracy = test_accuracy
                checkpoint['best_accuracy'] = best_accuracy
                if iter_num > 0:
                    print(f"saving checkpoint to {out_dir}/{ckpt_path_name}")
                    ending = '_acc.pt' if not save_all_intermediate else f'_acc_{iter_num}.pt'
                    torch.save(checkpoint, os.path.join(out_dir, ckpt_path_name.split('.pt')[0]+ending))
            if eval_addition_ar and test_accuracy_ar > best_accuracy_ar or always_save_checkpoint:
                best_accuracy_ar = test_accuracy_ar
                checkpoint['best_accuracy_ar'] = best_accuracy_ar
                if iter_num > 0:
                    print(f"saving checkpoint to {out_dir}/{ckpt_path_name}")
                    torch.save(checkpoint, os.path.join(out_dir, ckpt_path_name.split('.pt')[0]+'_acc_ar.pt'))
            
        if iter_num == 0 and eval_only:
            break

        # forward backward update, with optional gradient accumulation to simulate larger batch size
        # and using the GradScaler if data type is float16
        for micro_step in range(gradient_accumulation_steps):
            if ddp:
                # in DDP training we only need to sync gradients at the last micro step.
                # the official way to do this is with model.no_sync() context manager, but
                # I really dislike that this bloats the code and forces us to repeat code
                # looking at the source of that context manager, it just toggles this variable
                model.require_backward_grad_sync = (micro_step == gradient_accumulation_steps - 1)
            with ctx:
                if not autoregressive_training:
                    logits, loss = model(X, Y, causal_training=causal_training, attn_mask=M)
                else:
                    logits, loss = model.autoregressive_training(X, Y, W, max_new_tokens=Y.shape[-1], attn_mask=M)
            # immediately async prefetch next batch while model is doing the forward pass on the GPU
            X, Y, M, W = get_batch('train')
            # backward pass, with gradient scaling if training in fp16
            scaler.scale(loss).backward()
        # clip the gradient
        if grad_clip != 0.0:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        # step the optimizer and scaler if training in fp16
        scaler.step(optimizer)
        scaler.update()
        # flush the gradients as soon as we can, no need for this memory anymore
        optimizer.zero_grad(set_to_none=True)

        # timing and logging
        t1 = time.time()
        dt = t1 - t0
        t0 = t1
        if iter_num % log_interval == 0 and master_process:
            lossf = loss.item() # loss as float. note: this is a CPU-GPU sync point
            if local_iter_num >= 5: # let the training loop settle a bit
                mfu = raw_model.estimate_mfu(batch_size * gradient_accumulation_steps, dt)
                running_mfu = mfu if running_mfu == -1.0 else 0.9*running_mfu + 0.1*mfu
            print(f"iter {iter_num}: loss {lossf:.4f}, time {dt*1000:.2f}ms, mfu {running_mfu*100:.2f}%")
        iter_num += 1
        local_iter_num += 1

        if 'gpt2' in init_from and master_process and (iter_num % print_interval == 0):
            print(f"Prompt model after {iter_num} iterations:")
            print_model_output(model, encode, decode, device=device)
            if add_space:
                print_model_output(model, encode, decode, device=device, max_new_tokens=5, start='4 2 + 7 9 =')
            else: 
                print_model_output(model, encode, decode, device=device, max_new_tokens=3, start='$42+79=')
                print_model_output(model, encode, decode, device=device, max_new_tokens=3, start='42+79=')


        if test_accuracy > 99:
            break

        # termination conditions
        if iter_num > max_iters:
            break

    if save_final:
        print(f"saving final checkpoint to {out_dir}")
        torch.save(checkpoint, os.path.join(out_dir, ckpt_path_name.split('.pt')[0]+'_final.pt'))

    if ddp:
        destroy_process_group()
        
    wandb.finish()
    