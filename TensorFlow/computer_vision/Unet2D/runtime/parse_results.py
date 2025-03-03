# Copyright (c) 2019, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
###############################################################################
# Copyright (C) 2020-2021 Habana Labs, Ltd. an Intel Company
###############################################################################
# Changes:
# - removed exec_mode from argparser
# - replaced gpu specific env choices to hpu

import os
import numpy as np

import argparse


def process_performance_stats(timestamps, batch_size, mode):
    """ Get confidence intervals

    :param timestamps: Collection of timestamps
    :param batch_size: Number of samples per batch
    :param mode: Estimator's execution mode
    :return: Stats
    """
    timestamps_ms = 1000 * timestamps
    throughput_imgps = (1000.0 * batch_size / timestamps_ms).mean()
    stats = {f"throughput_{mode}": throughput_imgps,
             f"latency_{mode}_mean": timestamps_ms.mean()}
    for level in [90, 95, 99]:
        stats.update({f"latency_{mode}_{level}": np.percentile(timestamps_ms, level)})

    return stats


def parse_convergence_results(path, environment):
    dice_scores = []
    ce_scores = []
    logfiles = [f for f in os.listdir(path) if "log" in f and environment in f]
    if not logfiles:
        raise FileNotFoundError("No logfile found at {}".format(path))
    for logfile in logfiles:
        with open(os.path.join(path, logfile), "r") as f:
            content = f.readlines()[-1]
        if "eval_dice_score" not in content:
            print("Evaluation score not found. The file", logfile, "might be corrupted.")
            continue
        dice_scores.append(float([val for val in content.split("  ")
                                  if "eval_dice_score" in val][0].split()[-1]))
        ce_scores.append(float([val for val in content.split("  ")
                                if "eval_ce_loss" in val][0].split()[-1]))
    if dice_scores:
        print("Evaluation dice score:", sum(dice_scores) / len(dice_scores))
        print("Evaluation cross-entropy loss:", sum(ce_scores) / len(ce_scores))
    else:
        print("All logfiles were corrupted, no loss was obtained.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="UNet-medical-utils")

    parser.add_argument('--model_dir',
                        type=str,
                        required=True)

    parser.add_argument('--env',
                        choices=['fp32_1hpu', 'fp32_8hpu', 'bf16_1hpu', 'bf16_8hpu'],
                        type=str,
                        required=True)

    args = parser.parse_args()
    parse_convergence_results(path=args.model_dir, environment=args.env)
    print()
