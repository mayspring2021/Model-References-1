###############################################################################
# Copyright (C) 2020-2021 Habana Labs, Ltd. an Intel Company
###############################################################################

import sys
import os
from pathlib import Path
import io
import socket
import argparse
import TensorFlow.nlp.albert.albert_mrpc_main as albert_mrpc_main
import TensorFlow.nlp.albert.albert_squad_main as albert_squad_main
import TensorFlow.nlp.albert.albert_pretraining_overfit_main as albert_pretraining_overfit_main
from central.habana_model_runner_utils import get_canonical_path, get_canonical_path_str, is_valid_multi_node_config, get_multi_node_config_nodes
from central.multi_node_utils import run_per_ip
import TensorFlow.nlp.albert.download.download_pretrained_model as download_pretrained_model

ALBERT_ARGPARSER_HELP = ''


class Albert(object):
  def __init__(self):
    super(Albert, self).__init__()
    self.pretrained_url = "https://storage.googleapis.com/albert_models/"
    self.pretrained_model = ''

  def download_pretrained_model(self, horovod_run):
    try:
      if horovod_run and is_valid_multi_node_config():
        download_pretrained_model_path = Path(__file__).parent.joinpath(
            'download').joinpath('download_pretrained_model.py')
        run_per_ip(f"python3 {str(download_pretrained_model_path)} {self.pretrained_url} {self.pretrained_model}", [
                   'MULTI_HLS_IPS', 'PYTHONPATH'], False)
      else:
        download_pretrained_model.download_pretrained_model_r(self.pretrained_url, self.pretrained_model)
    except Exception as exc:
      raise RuntimeError(f"Error in {self.__class__.__name__} download_pretrained_model()") from exc

  def pretraining(self, args):
    if args.test_set is None:
      print(ALBERT_ARGPARSER_HELP)
    if args.test_set == "overfit":
      if args.train_steps:
        t = args.train_steps
      else:
        t = 200
      if args.warmup_steps:
        w = args.warmup_steps
      else:
        w = 10
      if args.batch_size:
        b = args.batch_size
      else:
        b = 32
      if args.max_seq_length:
        s = args.max_seq_length
      else:
        s = 128
      print(f"running overfit on ALBERT {args.model_variant} {self.pretrained_model}; {t} train steps, {w} warmup steps, {b} batch, {s} max_seq_length; BF16: {os.environ.get('TF_ENABLE_BF16_CONVERSION')}")
      overfit_runner = albert_pretraining_overfit_main.AlbertPretrainingOverfit(
          args, t, w, b, s, self.pretrained_model)
      overfit_runner.run()
    else:
      raise Exception("Incorrect test set passed to -t option")

  def finetuning(self, args):
    if args.test_set is None:
      print(ALBERT_ARGPARSER_HELP)
    if args.test_set == "mrpc":
      if args.train_steps:
        train_steps = args.train_steps
      else:
        train_steps = 800
      if args.warmup_steps:
        warmup_steps = args.warmup_steps
      else:
        e = 200
      if args.batch_size:
        b = args.batch_size
      else:
        if args.data_type == "bf16":
          b = 64
        else:
          b = 32
      if args.max_seq_length:
        s = args.max_seq_length
      else:
        s = 128
      print(
          f"running MRPC on ALBERT {args.model_variant} {self.pretrained_model} train_steps: {train_steps} warmup_steps: {warmup_steps} BF16: {os.environ.get('TF_ENABLE_BF16_CONVERSION')} BS: {b} T: {s}")
      mrpc_runner = albert_mrpc_main.AlbertFinetuningMRPC(args, train_steps, warmup_steps, b, s, self.pretrained_model)
      mrpc_runner.run()
    elif args.test_set == "squad":
      if args.epochs:
        e = args.epochs
      else:
        e = 2
      if args.batch_size:
        b = args.batch_size
      else:
        if args.data_type == "bf16":
          b = 24
        else:
          b = 10
      if args.max_seq_length:
        s = args.max_seq_length
      else:
        s = 384
      print(
          f"running SQUAD on ALBERT {args.model_variant} {self.pretrained_model} epochs: {e} BF16: {os.environ.get('TF_ENABLE_BF16_CONVERSION')} BS: {b} T: {s}")
      squad_runner = albert_squad_main.AlbertFinetuningSQUAD(args, e, b, s, self.pretrained_model)
      squad_runner.run()
    else:
      raise Exception("Incorrect test set passed to -t option")


class AlbertLarge(Albert):
  """docstring for AlbertLarge"""

  def __init__(self):
    super(AlbertLarge, self).__init__()
    self.pretrained_model = "albert_large_v1"


class AlbertBase(Albert):
  """docstring for AlbertBase"""

  def __init__(self):
    super(AlbertBase, self).__init__()
    self.pretrained_model = "albert_base_v1"


class AlbertArgparser(argparse.ArgumentParser):
  """docstring for AlbertArgparser"""

  def __init__(self):
    super(AlbertArgparser, self).__init__()
    self.add_argument('-c', '--command', required=True, metavar='<command>',
                      choices=['pretraining', 'finetuning'], help='Command, possible values: pretraining, finetuning')
    self.add_argument('-d', '--data_type', required=True, metavar='<data_type>',
                      choices=['fp32', 'bf16'], help='Data type, possible values: fp32, bf16')
    self.add_argument('-m', '--model_variant', required=True, metavar='<model>', choices=[
                      'base', 'large'], help='Model variant, possible values: base, large')
    self.add_argument('--albert-config-dir', required=False, metavar='<albert_config_dir>', type=str,
                      help="Path to directory containing albert config files needed for chosen training type. If not specified the zip file will be downloaded.")
    self.add_argument('-o', '--output_dir', metavar='<dir>', help='Output directory (estimators model_dir)')
    self.add_argument('-v', '--use_horovod', metavar='<num_workers_per_hls>', type=int, required=False,
                      help='Use Horovod for training. num_workers_per_hls parameter is optional and defaults to 8')
    self.add_argument('-t', '--test_set', metavar='<test_set>', default='mrpc', choices=[
                      'overfit', 'mrpc', 'squad'], help='Benchmark dataset, possible finetuning values: mrpc, squad; possible pretraining values: overfit')
    self.add_argument('-e', '--epochs', metavar='<val>',
                      help='Number of epochs. If not set defaults to 3.0 for mrpc, 2.0 for squad')
    self.add_argument('-s', '--max_seq_length', metavar='<val>', help='Number of tokens in each sequence')
    self.add_argument('--train_steps', metavar='<val]>', help='Number of train steps for pretraining. Default: 200 for overfit')
    self.add_argument('--warmup_steps', metavar='<val>',
                      help='Number of warmup steps for pretraining. Default: 10 for overfit')
    self.add_argument('--save_ckpt_steps', metavar='<val1>', type=int, default=100,
                      help='How often to save the model checkpoint. Default: 100')
    self.add_argument('-b', '--batch_size', metavar='<batch_size>', help='Batch size')
    self.add_argument('--learning_rate', metavar='<learning_rate>', required=False,
                      type=float, default=2e-5, help='Learning rate')
    self.add_argument('--dataset_path', metavar='<dataset_path>', required=False,
                      type=str, default='', help='Path to training dataset')
    self.add_argument('--init_checkpoint_path', metavar='<overfit_init_checkpoint_path>', required=False,
                      type=str, default='', help='Init checkpoint path for use in overfit pretraining')


def prevent_mpirun_execution():
  if os.environ.get('OMPI_COMM_WORLD_SIZE'):
    raise RuntimeError(
        "This script is not meant to be run from within an OpenMPI context (using mpirun). Use -v parameter to enable the multi-node mode.")


def check_data_type_and_tf_bf16_conversion(args):
  if args.data_type == 'bf16':
    if os.environ.get('TF_ENABLE_BF16_CONVERSION') is None:
      os.environ['TF_ENABLE_BF16_CONVERSION'] = "bert"
  elif args.data_type != 'fp32':
    raise Exception("data_type can only be \'bf16\' or \'fp32\'")


def check_and_log_synapse_env_vars():
  run_tpc_fuser_env = os.environ.get('RUN_TPC_FUSER')
  if run_tpc_fuser_env is not None:
    print(f"RUN_TPC_FUSER={run_tpc_fuser_env}")
  habana_synapse_logger_env = os.environ.get('HABANA_SYNAPSE_LOGGER')
  if habana_synapse_logger_env is not None:
    print(f"HABANA_SYNAPSE_LOGGER={habana_synapse_logger_env}")
  log_level_all_env = os.environ.get('LOG_LEVEL_ALL')
  if log_level_all_env is not None:
    print(f"LOG_LEVEL_ALL={log_level_all_env}")


def get_model(args):
  try:
    the_map = {
        'base': AlbertBase,
        'large': AlbertLarge,
    }
    return the_map[args.model_variant]()
  except Exception as exc:
    print("Error: Incorrect model passed to -m option")
    raise RuntimeError("Error in get_model") from exc


def main():
  try:
    prevent_mpirun_execution()
    args = AlbertArgparser().parse_args()

    old_stdout = sys.stdout
    new_stdout = io.StringIO()
    sys.stdout = new_stdout
    AlbertArgparser().print_help()
    ALBERT_ARGPARSER_HELP = new_stdout.getvalue()
    sys.stdout = old_stdout

    if os.environ.get('PYTHONPATH'):
      os.environ['PYTHONPATH'] = get_canonical_path_str("./") + ":" + \
        get_canonical_path_str("../../common") + ":" + \
        get_canonical_path_str("../../") + ":" + \
        get_canonical_path_str("../../../central/") + ":" + os.environ.get('PYTHONPATH')
    else:
      os.environ['PYTHONPATH'] = get_canonical_path_str("./") + ":" + \
        get_canonical_path_str("../../common") + ":" + \
        get_canonical_path_str("../../") + ":" + \
        get_canonical_path_str("../../../central/")

    print(f"{__file__}: PYTHONPATH = {os.environ.get('PYTHONPATH')}")

    check_data_type_and_tf_bf16_conversion(args)
    check_and_log_synapse_env_vars()
    model = get_model(args)
    if args.albert_config_dir is not None:
      model.pretrained_model = args.albert_config_dir
    # This downloads the model on all remote IPs if env variable MULTI_HLS_IPS is set
    if args.use_horovod is not None:
      model.download_pretrained_model(True)
    else:
      model.download_pretrained_model(False)
    the_map = {
        "pretraining": model.pretraining,
        "finetuning": model.finetuning
    }
    the_map[args.command](args)
  except Exception as exc:
    raise RuntimeError("Error in demo_albert") from exc


if "__main__" == __name__:
  main()
