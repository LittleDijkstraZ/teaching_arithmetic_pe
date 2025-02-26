# Define the parameters in a dictionary
import os
import glob
from click import command
import pandas as pd
from functools import partial

from sympy import use
from torch import permute


def run_training(out_name,
    kwargs,):
    # layerwise_pe, use_residual = args

    # pe_type='original'
    params = {
        'max_iters': kwargs['max_iters'] if 'max_iters' in kwargs else 5000, # 10000
        # 'max_iters': 10000, # increase to see if hard-to-converge cases can converge
        'lr_decay_iters':  kwargs['max_iters'] if 'max_iters' in kwargs else 5000, # keep the original training schedule
        'general_seed': kwargs['general_seed'] if 'general_seed' in kwargs else 888,
        'out_dir': 'outputs_permute',
        'pe_type': kwargs['use_pe'],  # or 'sin'
        # 'learning_rate': 0.00055221,
        # 'warmup_iters': 422,

        # 'learning_rate': 0.00038441, # 1202
        # 'warmup_iters': 797,
        
        # 'learning_rate': 0.00026441, # 1202 manual
        # 'warmup_iters': 797,

        # 'learning_rate': 0.000125, # 0126 manual
        # 'warmup_iters': 600,
        
        # 'learning_rate': 0.001, # original setting
        # 'warmup_iters': 200,

        'learning_rate': 0.00026441, # 0126 try to preven rank degen
        'warmup_iters': 400,

        ### for non causal task
        # 'learning_rate': 0.000026441, # 0126 try to preven rank degen
        # 'warmup_iters': 200,


        # 'learning_rate': kwargs['learning_rate'] if 'learning_rate' in kwargs else 0.0002644, # 0126 try to preven rank degen
        # 'warmup_iters': kwargs['max_iters']*0.1 if 'max_iters' in kwargs else 400,

        'permute_length': kwargs['permute_length'] if 'permute_length' in kwargs else None,
        'use_residual': kwargs['use_residual'],
        'layerwise_pe': kwargs['layerwise_pe'],
        'permute': kwargs['permute'] if 'permute' in kwargs else False, 
        'not_causal': kwargs['not_causal'],
    }

    params['out_name'] = out_name
    if 'message' in kwargs and len(kwargs['message']) > 0:
        params['message'] = '_'+kwargs['message'] 
    else:
        params['message'] = ''
    
    # Construct the output directory and other variables
    # wandb_run_name = f"addition_reverse_sd{params['general_seed']}{params['message']}"
    # wandb_run_name = f"parity_sd{params['general_seed']}{params['message']}"
    # wandb_run_name = f"sumd_sd{params['general_seed']}{params['message']}"\

    choice = kwargs['choice']
    wandb_run_name = f"{choice}_sd{params['general_seed']}{params['message']}"  

    output_directory = os.path.join(params['out_dir'], f"{params['out_name']}/{wandb_run_name}")
    current_exist = os.listdir(os.path.join(params['out_dir'], f"{params['out_name']}"))
    tmp_pe = params['pe_type'] if params['pe_type'] != 'original' else '' 
    for dir in current_exist:
        if f"sd{params['general_seed']}" in dir \
            and f'_res={params["use_residual"]}' in dir\
            and f"{tmp_pe}" in dir:
            print(f"Already exist: {dir}")
            return
    print(f'need to run', f"sd{params['general_seed']}", f'_res={params["use_residual"]}', f"{tmp_pe}") 
    wandb_project = params['out_name']

    # Construct the command using parameters from the dictionary
    layerwise_pe_repr = '['+','.join(map(str,params['layerwise_pe']))+']' if type(params['layerwise_pe']) is list else str(params['layerwise_pe'])
    use_residual_repr = '['+','.join(map(str,params['use_residual']))+']' if type(params['use_residual']) is list else str(params['use_residual'])
    
    if isinstance(params['permute'], list) and str in [type(i) for i in params['permute']]:
        permute_repr = '['
        for i in params['permute']:
            permute_repr += str(i) if type(i)!=str else "\\"+"'"+i+"\\"+"'"
            permute_repr += ','
        permute_repr += ']'
    else:
        permute_repr = '['+','.join(map(str,params['permute']))+']' if type(params['permute']) is list else str(params['permute'])
    print(permute_repr)
    not_casual_repr = '['+','.join(map(str,params['not_causal']))+']' if type(params['not_causal']) is list else str(params['not_causal'])
    command_params = {
        'use_pe': params['pe_type'],
        'use_residual': use_residual_repr,
        'max_iters': params['max_iters'],
        'lr_decay_iters': params['lr_decay_iters'],
        'layerwise_pe': layerwise_pe_repr,
        'permute': permute_repr,
        'permute_length': params['permute_length'],
        'general_seed': params['general_seed'],
        'not_causal': not_casual_repr,
        'out_dir': output_directory,
        'wandb_run_name': wandb_run_name,
        'learning_rate': params['learning_rate'],
        'warmup_iters': params['warmup_iters'],
        'wandb_project': wandb_project,
    }
    # List of keyword argument names
    kwarg_names = [
        'use_flash', 
        'n_layer', 
        'no_att_residual', 
        'no_mlp_residual', 
        'batch_size', 
        'causal_training', 
        'save_best_loss', 
        'save_final', 
        'autoregressive_training', 
        'save_all_intermediate',
        'layer_pe'
    ]

    # Iterate over the list and update command_params if the key exists in kwargs
    for name in kwarg_names:
        if name in kwargs:
            command_params[name] = kwargs[name]

    # command = "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py "
    # command = "python3 train.py pe_info/config2_pe/parity/jason_train_addition_bal.py "
    # command = "python3 train.py pe_info/config2_pe/sumd/jason_train_addition_bal.py "
    # command = "python3 train.py pe_info/config2_pe/oddc/jason_train_addition_bal.py "
    command = kwargs['command']
        

    for key, value in command_params.items():
        command += f" --{key}={value}"
    print(command)
    os.system(command)




if __name__ == "__main__":
    out_dir = "./outputs_permute"

    
    # ==================== 1203 ====================
    # out_name = f"out3_control" # out4_1203 causal didn't converge.


    # current problems
    # 1. loss is weird


    # use_residual_list0 = [[0,3,4,5]]s
    # use_residual_list0 = [False]

    # not_causal_list = [[1,],[0,], [0, 1]]

    # control

    # use_residual_list = [[3, 4, 5]]
    use_residual_list1 = [[i for i in range(6) if i not in [j, j+1, j+2]] for j in range(4)]
    use_residual_list2 = [[i for i in range(6) if i not in [j, j+1]] for j in range(5)]

    # use_residual_list2 = [[i for i in range(6) if i not in [j, j+2]] for j in range(4)]
    # use_residual_list3 = [[i for i in range(6) if i not in [j,]] for j in range(6)]
    use_residual_list4 = [[i for i in range(6)]]
    
    # use_residual_list4 = [[2,3,4,5], [3, 4, 5], [4, 5], [5], []]
    # use_residual_list4 = [[1,2,3,4,5], [2,3,4,5], [3, 4, 5], [4, 5]]

    # use_residual_list_all = [[i for i in range(6) if i not in [j, j+1, j+2, j+3, j+4]] for j in range(2)] \
    #     + [[i for i in range(6) if i not in [j, j+1, j+2, j+3]] for j in range(3)] \
    #     + [[i for i in range(6) if i not in [j, j+1, j+2]] for j in range(4)] \
    #     + [[i for i in range(6) if i not in [j, j+1]] for j in range(5)] \
    #     + [[i for i in range(6) if i not in [j,]] for j in range(6)] \
    #     + [[i for i in range(6)]]s
    # use_residual_list3 = [[i for i in range(6) if i not in [j,]] for j in range(2, 6)]
    seeds = [240+i for i in range(0, 1)]

    # use_residual_list_all = [[]] \
    #     + [[i for i in range(6) if i not in [j, j+1, j+2, j+3, j+4]] for j in range(2)] \
    #     + [[i for i in range(6) if i not in [j, j+1, j+2, j+3]] for j in range(3)] \
    #     + [[i for i in range(6) if i not in [j, j+1, j+2]] for j in range(4)] \
    #     + [[i for i in range(6) if i not in [j, j+1]] for j in range(5)] \
    #     + [[i for i in range(6) if i not in [j,]] for j in range(6)] \
    #     + [[i for i in range(6)]]

    # '''for permute'''
    # use_residual_list_all = [[i for i in range(6) if i not in [j, j+1, j+2]] for j in range(4)] \
    #     + [[i for i in range(6) if i not in [j, j+1]] for j in range(5)] \
    #     + [[i for i in range(6) if i not in [j,]] for j in range(6)] \
    #     + [[i for i in range(6)]]

    '''for permute but not losing rescon'''
    # use_residual_list_all = [[0], [2], [0,1], [1,2], [0, 1, 2], [3, 4, 5], [0,1,2,3,4], [0,1,2,3,4,5]]
    use_residual_list_all = [[]]

    # use_residual_list_all = [[0], [2]]



    # use_residual_list_all = [[i for i in range(6) if i not in j] for j in use_residual_list_all]

    commands_dict = {
        # "add3": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_nc": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_lwp": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_shuffle": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_shuffle_6": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_8_lwp": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_8": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_16": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_8_original": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_8_rotary": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_8_sin": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_8_T5": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_remove_8_nope": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",

        "add3_ref_nope": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_ref_sin": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_ref_original": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_ref_T5": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",
        "add3_ref_rotary": "python3 train.py pe_info/config2_pe/addition/reverse/jason_train_addition_bal.py ",




        "mod3" : "python3 train.py pe_info/config2_pe/mod3/jason_train_addition_bal.py ",
        "mod3_nc" : "python3 train.py pe_info/config2_pe/mod3/jason_train_addition_bal.py ",

        "modp" : "python3 train.py pe_info/config2_pe/modp/jason_train_addition_bal.py ",
        "modp_nc" : "python3 train.py pe_info/config2_pe/modp/jason_train_addition_bal.py ",

        "mods": "python3 train.py pe_info/config2_pe/mods/jason_train_addition_bal.py ",
        "mods_nc": "python3 train.py pe_info/config2_pe/mods/jason_train_addition_bal.py ",

        "parity": "python3 train.py pe_info/config2_pe/parity/jason_train_addition_bal.py ",
        "parity_nc_repeat": "python3 train.py pe_info/config2_pe/parity/jason_train_addition_bal.py ",
        "sumd_c": "python3 train.py pe_info/config2_pe/sumd/jason_train_addition_bal.py ",
        "oddc": "python3 train.py pe_info/config2_pe/oddc/jason_train_addition_bal.py "
    }
    for seed in seeds:

        # for choice in ["mods", "mods_nc", "mod3", "mod3_nc", "modp", "modp_nc",]:
        for choice in [ "add3_ref_nope", "add3_ref_sin", "add3_ref_original"]:

        # for choice in [ "add3_ref_T5", "add3_ref_rotary"]:
            # choice = "mod3_nc"
            causal_training = True
            autoregressive_training = False

            batch_size = 4096 if not causal_training else 256
            max_iters = 2000 if not causal_training else 5000
            # learning_rate = 0.000026441 if not causal_training else  0.000026441
            learning_rate = 0.0000016441 if not causal_training else  0.0000016441

            warmup_iters = 400 if not causal_training else 400


            # batch_size = 2048 if not causal_training else 256
            # max_iters = 2000 if not causal_training else 5000
            # learning_rate = 0.000026441 if not causal_training else  0.00026441
            # warmup_iters = 200 if not causal_training else 400
            # batch_size = 256
            # max_iters = 5000 
            # learning_rate = 0.0001
            # warmup_iters = 400

            
            # for use_pe in ['nope', 'original']: # 'original''nope', 

            # for use_residual_list in [use_residual_list2, use_residual_list3]: # use_residual_list1, use_residual_list2, 
            # for use_residual_list in [use_residual_list1, use_residual_list2]: # use_residual_list1, use_residual_list2, 
            for use_residual_list in [use_residual_list_all]: # use_residual_list1, use_residual_list2, 
                

                # no_att_residual_list = [True]
                # no_mlp_residual_list = [True]
                bval = True if 'nc' in choice else False
                not_causal_list = [bval] * len(use_residual_list)
                # not_causal_list = [False]
                # bs = [512]

                # n_layers = [,]
                # no SC[i] SC[i+1] yes lwp=True
                # use_residual_list = [[j for j in range(6) if j not in [i, i+1]] for i in range(5)]
                # layerwise_pe_list = [True for i in range(5)]
                

                # do a multi-processing, using 2 processes at a time
                from multiprocessing import Pool
                from functools import partial
                

                # for seed in [222, 333, 444]:
                # for use_pe in ['nope', 'original']: # 'original''nope',
                # for use_pe in ['original', 'nope']: # 'original''nope',
                # for use_pe in ['nope']: # 'original''nope',
                # for use_pe in ['original', 'nope']: # 'original''nope',
                for n_layers in [6, 12]:
                    for use_pe in [choice.split('_')[-1]]: # 'original''nope',
                        layer_pe = choice.split('_')[-1]
                        if 'shuffle' in choice:
                            permuteMap = lambda use_residual_list: ["shuffle" if l in use_residual_list else 0 for l in range(n_layers)]
                        elif 'remove' in choice:
                            permuteMap = lambda use_residual_list: ["remove" if l in use_residual_list else 0 for l in range(n_layers)]
                        else:
                            permuteMap = lambda use_residual_list: use_residual_list

                        out_name = f"{choice}_abs" if use_pe=='original' else f"{choice}_{use_pe}" # out4_1203 causal didn't converge.
                        if layer_pe != use_pe:
                            out_name += f"_layer_pe"
                        os.makedirs(f"{out_dir}/{out_name}", exist_ok=True)

                        pool = Pool(1)
                        func = partial(run_training, out_name)
                        args = [{
                            'not_causal': not_causal_list[i],
                            # 'use_residual': use_residual_list[i],
                            'use_residual': True,
                            'n_layer': n_layers,
                            'use_pe': use_pe,
                            'general_seed': seed,
                            'choice': choice,

                            'causal_training': causal_training,
                            'batch_size': batch_size, 
                            'max_iters': max_iters,
                            'learning_rate': learning_rate,
                            'warmup_iters': warmup_iters,
                            
                            'command': commands_dict[choice],  
                            'save_best_loss': False,
                            'save_final': False,
                            'autoregressive_training': autoregressive_training,
                            # 'permute': permuteMap(use_residual_list[i]), # for permute, set the layers to be permuted
                            # 'permute_length': 8,
                            # 'permute': False,
                            'save_all_intermediate': True,

                            # 'no_att_residual': no_att_residual_list[i],
                            # 'no_mlp_residual': no_mlp_residual_list[i],
                            # 'batch_size': bs[i],
                            # 'message': '',
                            # 'layerwise_pe': [0],
                            'layerwise_pe': False,
                            'layer_pe': layer_pe,
                            # 'use_flesh': True,
                            # 'layerwise_pe_list': layerwise_pe_list[i],
                        } for i in range(len(use_residual_list))]
                        # for arg in args:
                            # func(arg)
                        pool.map(func, args)
                        pool.close()   

                    # implement a teacher forcing