# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Dict, List, Tuple

import torch
from rl_utils.common import DictDataset


def log_finished_rewards(
    rollouts,
    rolling_ep_rewards: torch.Tensor,
    logger,
) -> torch.Tensor:
    """
    :param rolling_ep_rewards: tensor of shape (num_envs,)
    """
    num_envs, num_steps = rollouts["reward"].shape[:2]
    done_episodes_rewards = []
    for env_i in range(num_envs):
        for step_i in range(num_steps):
            rolling_ep_rewards[env_i] += rollouts["reward"][env_i, step_i].item()
            if rollouts["done"][env_i, step_i].item():
                done_episodes_rewards.append(rolling_ep_rewards[env_i].item())
                rolling_ep_rewards[env_i] = 0
    logger.collect_info_list("inferred_episode_reward", done_episodes_rewards)
    return rolling_ep_rewards


def create_next_obs(dataset: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    obs = dataset["observations"].detach()

    # final_final_obs = dataset["infos"][-1]["final_obs"]

    # next_obs = torch.cat([obs[1:], final_final_obs.unsqueeze(0)], 0)
    next_obs = dataset["next_observations"].detach()
    num_eps = 1
    for i in range(obs.shape[0] - 1):
        cur_info = dataset["infos"][i]
        if "final_obs" in cur_info:
            num_eps += 1
            next_obs[i] = cur_info["final_obs"].detach()

    if num_eps != dataset["terminals"].sum():
        raise ValueError(
            f"Inconsistency in # of episodes {num_eps} vs {dataset['terminals'].sum()}"
        )
    dataset["next_observations"] = next_obs.detach()

    return dataset


def get_dataset_data(dataset_path: str, env_name: str):
    import json 
    dataset = json.load(open("expert_data.json", 'r'))
    dataset = {k: torch.tensor(v) for k, v in dataset.items()}
    dataset["infos"] = [{} for _ in range(dataset["observations"].shape[0])]
    return create_next_obs(dataset)


def get_transition_dataset(dataset_path: str, env_name: str):
    dataset = get_dataset_data(dataset_path, env_name)
    return DictDataset(
        dataset,
        [
            "observations",
            "actions",
            "rewards",
            "terminals",
            "next_observations",
        ],
    )
