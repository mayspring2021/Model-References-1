###############################################################################
# Copyright (C) 2020-2021 Habana Labs, Ltd. an Intel Company
###############################################################################

import os
import sys
from pathlib import Path
import subprocess
from central.habana_model_runner_utils import HabanaEnvVariables, print_env_info, get_canonical_path, get_canonical_path_str, is_valid_multi_node_config, get_multi_node_config_nodes
from central.training_run_config import TrainingRunHWConfig
from central.multi_node_utils import run_per_ip
import TensorFlow.nlp.bert.download.download_dataset as download_dataset
import central.prepare_output_dir as prepare_output_dir

class AlbertFinetuningMRPC(TrainingRunHWConfig):
    def __init__(self, args, train_steps, warmup_steps, batch_size, max_seq_len, pretrained_model):
        super(AlbertFinetuningMRPC, self).__init__(args)
        self.args = args
        self.train_steps = train_steps
        self.warmup_steps = warmup_steps
        self.batch_size = batch_size
        self.max_seq_len = max_seq_len
        self.pretrained_model = pretrained_model
        self.command = ''
        self.mrpc_habana_env_variables = {}
        self.args.dataset_path = Path(__file__).parent.joinpath("MRPC")
        if self.args.use_horovod is not None:
            # By default: HCL Streams:ON, ART:ON, SAO:ON
            self.mrpc_habana_env_variables = {'HABANA_USE_STREAMS_FOR_HCL' : 'true' ,
                                              'HABANA_USE_PREALLOC_BUFFER_FOR_ALLREDUCE' : 'true',
                                              'TF_DISABLE_SCOPED_ALLOCATOR' : 'true'}


    # Download the dataset on all remote IPs
    def download_dataset(self):
        try:
            if self.use_horovod and is_valid_multi_node_config():
                download_dataset_path = Path(__file__).parent.joinpath('download').joinpath('download_dataset.py')
                run_per_ip(f"python3 {str(download_dataset_path)} {self.args.dataset_path}", ['MULTI_HLS_IPS', 'PYTHONPATH'], False)
            else:
                download_dataset.download_dataset_r(self.args.dataset_path)
        except Exception as exc:
            raise RuntimeError(f"Error in {self.__class__.__name__} download_dataset()") from exc

    # Prepare the output directory on all remote IPs
    def prepare_output_dir(self):
        try:
            if self.args.use_horovod and is_valid_multi_node_config():
                prepare_output_dir_path = Path(__file__).parent.parent.parent.parent.joinpath('central').joinpath('prepare_output_dir.py')
                run_per_ip(f"python3 {str(prepare_output_dir_path)} {self.args.output_dir}", ['MULTI_HLS_IPS', 'PYTHONPATH'], False)
            else:
                prepare_output_dir.prepare_output_dir_r(self.args.output_dir)
        except Exception as exc:
            raise RuntimeError(f"Error in {self.__class__.__name__} prepare_output_dir()") from exc

    def build_command(self):
        try:
            run_classifier_path = Path(__file__).parent.joinpath('run_classifier.py')
            pretrained_model_path = get_canonical_path(self.pretrained_model)
            use_horovod_str = "true" if self.args.use_horovod else "false"
            vocab_path = str(pretrained_model_path.joinpath("30k-clean.vocab"))
            spm_path = str(pretrained_model_path.joinpath("30k-clean.model"))
            bcfg_path = str(pretrained_model_path.joinpath("albert_config.json"))
            ic_path = str(pretrained_model_path.joinpath("model.ckpt-best"))
            data_dir = Path(__file__).parent

            print(f"{self.__class__.__name__}: self.mpirun_cmd = {self.mpirun_cmd}")
            if self.mpirun_cmd == '':
                init_command = f"time python3 {str(run_classifier_path)}"
            else:
                init_command = f"time {self.mpirun_cmd} python3 {str(run_classifier_path)}"
            self.command = (
                f"{init_command}"
                f" --task_name=MRPC --do_train=true --do_eval=true --data_dir={data_dir}"
                f" --vocab_file={vocab_path}"
                f" --albert_config_file={bcfg_path}"
                f" --spm_model_file={spm_path}"
                f" --init_checkpoint={ic_path}"
                f" --max_seq_length={self.max_seq_len}"
                f" --train_batch_size={self.batch_size}"
                f" --learning_rate={self.args.learning_rate}"
                f" --train_step={self.train_steps}"
                f" --warmup_step={self.warmup_steps}"
                f" --output_dir={get_canonical_path_str(self.args.output_dir)}"
                f" --use_horovod={use_horovod_str}"
            )
            print('albert_mrpc_utils::self.command = ', self.command)
        except Exception as exc:
            raise RuntimeError(f"Error in {self.__class__.__name__} build_command()") from exc

    def run(self):
        try:
            self.download_dataset()
            self.prepare_output_dir()
            print("*** Running ALBERT training...\n\n")
            run_config_env_vars = self.get_env_vars()
            print('run_config_env_vars = ', run_config_env_vars)
            with HabanaEnvVariables(env_vars_to_set=run_config_env_vars), \
                 HabanaEnvVariables(env_vars_to_set=self.mrpc_habana_env_variables):
                self.build_command()
                print_env_info(self.command, run_config_env_vars)
                print_env_info(self.command, self.mrpc_habana_env_variables)
                print(f"{self.__class__.__name__} run(): self.command = {self.command}")
                sys.stdout.flush()
                sys.stderr.flush()
                with subprocess.Popen(self.command, shell=True, executable='/bin/bash') as proc:
                    proc.wait()
        except Exception as exc:
            raise RuntimeError(f"Error in {self.__class__.__name__} run()") from exc
