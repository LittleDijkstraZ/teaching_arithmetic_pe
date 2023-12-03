# train a miniature character-level shakespeare model
# good for debugging and playing on macbooks and such

out_dir = 'out2/subtraction/ar_simple_randomA'
eval_interval = 1000 # keep frequent because we'll overfit
eval_iters = 200
log_interval = 10 # don't print too too often

# we expect to overfit on this small dataset, so only save when val improves
always_save_checkpoint = False

wandb_log = True # override via command line if you like
wandb_project = 'subtraction'
wandb_run_name = 'ar_simple_randomA'

data_type='text'
data_format='algo_reasoning'
operator='-'
dataset = 'bal'
batch_size = 16
block_size = 1024 # context of up to 256 previous characters
train_data_path = 'train_3digit_10000.txt'
# val_data_path = 'val.bin'
ckpt_path_name = 'ckpt.pt'
eval_addition = True
start = "FILE:data/bal/test_3digit_1000.txt"

algo_reason = True
simple = True
random_A = True
random_C = False


# baby GPT model :)
n_layer = 6
n_head = 6
n_embd = 384
dropout = 0.2

learning_rate = 1e-3 # with baby networks can afford to go a bit higher
max_iters = 20000
lr_decay_iters = 20000 # make equal to max_iters usually
beta2 = 0.99 # make a bit bigger because number of tokens per iter is small

warmup_iters = 00 # not super necessary potentially

device='cuda:0'

# on macbook also add
# device = 'cpu'  # run on cpu only
# compile = False # do not torch compile the model