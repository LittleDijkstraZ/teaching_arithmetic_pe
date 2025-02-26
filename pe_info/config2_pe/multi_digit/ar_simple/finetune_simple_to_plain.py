# train a miniature character-level shakespeare model
# good for debugging and playing on macbooks and such

num_digit = 4
multi_digit = True

init_from = 'resume'
resume_dir = f'out2/addition/ar_simple/ckpt_final.pt'

out_dir = f'out2_multidigit_ft_format/digit_{num_digit}/simple_to_plain'
eval_interval = 500 # keep frequent because we'll overfit
eval_iters = 200
log_interval = 10 # don't print too too often

# we expect to overfit on this small dataset, so only save when val improves
always_save_checkpoint = False

wandb_log = True # override via command line if you like
wandb_project = 'addition_multidigit_ft'
wandb_run_name = f'ft_{num_digit}digit_simple_to_plain'

data_type='text'
data_format='plain'
operator='+'
dataset = 'multi_digit'
batch_size = 16
block_size = 1024 # context of up to 256 previous characters
train_data_path = f'{num_digit}digit_20000.txt'
# val_data_path = 'val.bin'
ckpt_path_name = 'ckpt.pt'
eval_addition = True
start = f"FILE:data/multi_digit/test_{num_digit}digit_100.txt"


# baby GPT model :)
n_layer = 6
n_head = 6
n_embd = 384
dropout = 0.2

learning_rate = 5e-4 # with baby networks can afford to go a bit higher
max_iters = 20000
lr_decay_iters = 20000 # make equal to max_iters usually
beta2 = 0.99 # make a bit bigger because number of tokens per iter is small

warmup_iters = 00 # not super necessary potentially

device='cuda:0'

# on macbook also add
# device = 'cpu'  # run on cpu only
# compile = False # do not torch compile the model
