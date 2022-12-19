# http://proceedings.mlr.press/v97/han19a/han19a.pdf

import argparse
import os
import random
from statistics import mean
import subprocess
import math
import time
from distutils.util import strtobool
from typing import List
from itertools import cycle

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from gym.spaces import MultiDiscrete
from stable_baselines3.common.vec_env import VecEnvWrapper, VecMonitor, VecVideoRecorder
from torch.distributions.categorical import Categorical
from torch.utils.tensorboard import SummaryWriter

from gym_microrts import microrts_ai
from gym_microrts.envs.vec_env import (
    MicroRTSGridModeSharedMemVecEnv as MicroRTSGridModeVecEnv,
)


def parse_args():
    # fmt: off
    parser = argparse.ArgumentParser()
    parser.add_argument('--exp-name', type=str, default=os.path.basename(__file__).rstrip(".py"),
        help='the name of this experiment')
    parser.add_argument('--gym-id', type=str, default="MicroRTSGridModeVecEnv",
        help='the id of the gym environment')
    parser.add_argument('--learning-rate', type=float, default=2.5e-4,
        help='the learning rate of the optimizer')
    parser.add_argument('--seed', type=int, default=1,
        help='seed of the experiment')
    parser.add_argument('--total-timesteps', type=int, default=50000000,
        help='total timesteps of the experiments')
    parser.add_argument('--torch-deterministic', type=lambda x: bool(strtobool(x)), default=True, nargs='?', const=True,
        help='if toggled, `torch.backends.cudnn.deterministic=False`')
    parser.add_argument('--cuda', type=lambda x: bool(strtobool(x)), default=True, nargs='?', const=True,
        help='if toggled, cuda will not be enabled by default')
    parser.add_argument('--prod-mode', type=lambda x: bool(strtobool(x)), default=False, nargs='?', const=True,
        help='run the script in production mode and use wandb to log outputs')
    parser.add_argument('--capture-video', type=lambda x: bool(strtobool(x)), default=False, nargs='?', const=True,
        help='weather to capture videos of the agent performances (check out `videos` folder)')
    parser.add_argument('--wandb-project-name', type=str, default="microrts-py",
        help="the wandb's project name")
    parser.add_argument('--wandb-entity', type=str, default=None,
        help="the entity (team) of wandb's project")

    # Algorithm specific arguments
    parser.add_argument('--partial-obs', type=lambda x: bool(strtobool(x)), default=False, nargs='?', const=True,
        help='if toggled, the game will have partial observability')
    parser.add_argument('--n-minibatch', type=int, default=4,
        help='the number of mini batch')
    parser.add_argument('--num-bot-envs', type=int, default=0,
        help='the number of bot game environment; 16 bot envs measn 16 games')
    parser.add_argument('--num-selfplay-envs', type=int, default=24,
        help='the number of self play envs; 16 self play envs means 8 games')
    parser.add_argument('--num-steps', type=int, default=256,
        help='the number of steps per game environment')
    parser.add_argument('--gamma', type=float, default=0.99,
        help='the discount factor gamma')
    parser.add_argument('--gae-lambda', type=float, default=0.95,
        help='the lambda for the general advantage estimation')
    parser.add_argument('--ent-coef', type=float, default=0.01,
        help="coefficient of the entropy")
    parser.add_argument('--vf-coef', type=float, default=0.5,
        help="coefficient of the value function")
    parser.add_argument('--max-grad-norm', type=float, default=0.5,
        help='the maximum norm for the gradient clipping')
    parser.add_argument('--clip-coef', type=float, default=0.1,
        help="the surrogate clipping coefficient")
    parser.add_argument('--update-epochs', type=int, default=4,
        help="the K epochs to update the policy")
    parser.add_argument('--kle-stop', type=lambda x: bool(strtobool(x)), default=False, nargs='?', const=True,
        help='If toggled, the policy updates will be early stopped w.r.t target-kl')
    parser.add_argument('--kle-rollback', type=lambda x: bool(strtobool(x)), default=False, nargs='?', const=True,
        help='If toggled, the policy updates will roll back to previous policy if KL exceeds target-kl')
    parser.add_argument('--target-kl', type=float, default=0.03,
        help='the target-kl variable that is referred by --kl')
    parser.add_argument('--gae', type=lambda x: bool(strtobool(x)), default=True, nargs='?', const=True,
        help='Use GAE for advantage computation')
    parser.add_argument('--norm-adv', type=lambda x: bool(strtobool(x)), default=True, nargs='?', const=True,
        help="Toggles advantages normalization")
    parser.add_argument('--anneal-lr', type=lambda x: bool(strtobool(x)), default=True, nargs='?', const=True,
        help="Toggle learning rate annealing for policy and value networks")
    parser.add_argument('--clip-vloss', type=lambda x: bool(strtobool(x)), default=True, nargs='?', const=True,
        help='Toggles whether or not to use a clipped loss for the value function, as per the paper.')
    parser.add_argument('--num-models', type=int, default=100,
        help='the number of models saved')
    parser.add_argument('--max-eval-workers', type=int, default=4,
        help='the maximum number of eval workers (skips evaluation when set to 0)')
    parser.add_argument('--train-maps', nargs='+', default=["maps/8x8/basesWorkers8x8A.xml", "maps/16x16/basesWorkers16x16A.xml","maps/24x24/basesWorkers24x24A.xml"],
        help='the list of maps used during training')
    parser.add_argument('--eval-maps', nargs='+', default=["maps/8x8/basesWorkers8x8A.xml", "maps/16x16/basesWorkers16x16A.xml","maps/24x24/basesWorkers24x24A.xml"],
        help='the list of maps used during evaluation')
    parser.add_argument('--total-cycles', type=int, default=1)
    parser.add_argument('--random-maps', action=argparse.BooleanOptionalAction, type=bool)
    parser.add_argument('--spp-layers', nargs='+', type=int, default=[4])

    args = parser.parse_args()
    if not args.seed:
        args.seed = int(time.time())
    args.num_envs = args.num_selfplay_envs + args.num_bot_envs
    args.batch_size = int(args.num_envs * args.num_steps)
    args.minibatch_size = int(args.batch_size // args.n_minibatch)
    args.updates_per_map = args.total_timesteps // (args.total_cycles * len(args.train_maps) * args.batch_size)
    args.num_updates = args.updates_per_map * args.total_cycles * len(args.train_maps)
    args.save_frequency = max(1, int(args.num_updates // args.num_models))
    # fmt: on
    return args


class MicroRTSStatsRecorder(VecEnvWrapper):
    def __init__(self, env, gamma=0.99) -> None:
        super().__init__(env)
        self.gamma = gamma

    def reset(self):
        obs = self.venv.reset()
        self.raw_rewards = [[] for _ in range(self.num_envs)]
        self.ts = np.zeros(self.num_envs, dtype=np.float32)
        self.raw_discount_rewards = [[] for _ in range(self.num_envs)]
        return obs

    def step_wait(self):
        obs, rews, dones, infos = self.venv.step_wait()
        newinfos = list(infos[:])
        for i in range(len(dones)):
            self.raw_rewards[i] += [infos[i]["raw_rewards"]]
            self.raw_discount_rewards[i] += [
                (self.gamma ** self.ts[i])
                * np.concatenate((infos[i]["raw_rewards"], infos[i]["raw_rewards"].sum()), axis=None)
            ]
            self.ts[i] += 1
            if dones[i]:
                info = infos[i].copy()
                raw_returns = np.array(self.raw_rewards[i]).sum(0)
                raw_names = [str(rf) for rf in self.rfs]
                raw_discount_returns = np.array(self.raw_discount_rewards[i]).sum(0)
                raw_discount_names = ["discounted_" + str(rf) for rf in self.rfs] + ["discounted"]
                info["microrts_stats"] = dict(zip(raw_names, raw_returns))
                info["microrts_stats"].update(dict(zip(raw_discount_names, raw_discount_returns)))
                self.raw_rewards[i] = []
                self.raw_discount_rewards[i] = []
                self.ts[i] = 0
                newinfos[i] = info
        return obs, rews, dones, newinfos


# ALGO LOGIC: initialize agent here:
class CategoricalMasked(Categorical):
    def __init__(self, probs=None, logits=None, validate_args=None, masks=[], mask_value=None):
        logits = torch.where(masks.bool(), logits, mask_value)
        super(CategoricalMasked, self).__init__(probs, logits, validate_args)


class Transpose(nn.Module):
    def __init__(self, permutation):
        super().__init__()
        self.permutation = permutation

    def forward(self, x):
        return x.permute(self.permutation)


def layer_init(layer, std=np.sqrt(2), bias_const=0.0):
    torch.nn.init.orthogonal_(layer.weight, std)
    torch.nn.init.constant_(layer.bias, bias_const)
    return layer


# Adapted from https://github.com/revidee/pytorch-pyramid-pooling
class PyramidPooling(nn.Module):
    def __init__(self, levels, mode="max"):
        """
        General Pyramid Pooling class which uses Spatial Pyramid Pooling by default and holds the static methods for both spatial and temporal pooling.
        :param levels defines the different divisions to be made in the width and (spatial) height dimension
        :param mode defines the underlying pooling mode to be used, can either be "max" or "avg"
        :returns a tensor vector with shape [batch x 1 x n], where  n: sum(filter_amount*level*level) for each level in levels (spatial) or
                                                                    n: sum(filter_amount*level) for each level in levels (temporal)
                                            which is the concentration of multi-level pooling
        """
        super(PyramidPooling, self).__init__()
        self.levels = levels
        self.mode = mode

    def forward(self, x):
        return self.spatial_pyramid_pool(x, self.levels, self.mode)

    def get_output_size(self, filters):
        out = 0
        for level in self.levels:
            out += filters * level * level
        return out

    @staticmethod
    def spatial_pyramid_pool(previous_conv, levels, mode):
        """
        Static Spatial Pyramid Pooling method, which divides the input Tensor vertically and horizontally
        (last 2 dimensions) according to each level in the given levels and pools its value according to the given mode.
        :param previous_conv input tensor of the previous convolutional layer
        :param levels defines the different divisions to be made in the width and height dimension
        :param mode defines the underlying pooling mode to be used, can either be "max" or "avg"
        :returns a tensor vector with shape [batch x 1 x n],
                                            where n: sum(filter_amount*level*level) for each level in levels
                                            which is the concentration of multi-level pooling
        """
        num_sample = previous_conv.size(0)
        previous_conv_size = [int(previous_conv.size(2)), int(previous_conv.size(3))]
        for i in range(len(levels)):
            h_kernel = int(math.ceil(previous_conv_size[0] / levels[i]))
            w_kernel = int(math.ceil(previous_conv_size[1] / levels[i]))
            w_pad1 = int(math.floor((w_kernel * levels[i] - previous_conv_size[1]) / 2))
            w_pad2 = int(math.ceil((w_kernel * levels[i] - previous_conv_size[1]) / 2))
            h_pad1 = int(math.floor((h_kernel * levels[i] - previous_conv_size[0]) / 2))
            h_pad2 = int(math.ceil((h_kernel * levels[i] - previous_conv_size[0]) / 2))
            assert w_pad1 + w_pad2 == (w_kernel * levels[i] - previous_conv_size[1]) and \
                   h_pad1 + h_pad2 == (h_kernel * levels[i] - previous_conv_size[0])

            padded_input = nn.functional.pad(input=previous_conv, pad=[w_pad1, w_pad2, h_pad1, h_pad2],
                                 mode='constant', value=0)
            if mode == "max":
                pool = nn.MaxPool2d((h_kernel, w_kernel), stride=(h_kernel, w_kernel), padding=(0, 0))
            elif mode == "avg":
                pool = nn.AvgPool2d((h_kernel, w_kernel), stride=(h_kernel, w_kernel), padding=(0, 0))
            else:
                raise RuntimeError("Unknown pooling type: %s, please use \"max\" or \"avg\".")
            x = pool(padded_input)
            if i == 0:
                spp = x.reshape(num_sample, -1)
            else:
                spp = torch.cat((spp, x.reshape(num_sample, -1)), 1)

        return spp


class SpatialPyramidPooling(PyramidPooling):
    def __init__(self, levels, mode="max"):
        """
                Spatial Pyramid Pooling Module, which divides the input Tensor horizontally and horizontally
                (last 2 dimensions) according to each level in the given levels and pools its value according to the given mode.
                Can be used as every other pytorch Module and has no learnable parameters since it's a static pooling.
                In other words: It divides the Input Tensor in level*level rectangles width of roughly (previous_conv.size(3) / level)
                and height of roughly (previous_conv.size(2) / level) and pools its value. (pads input to fit)
                :param levels defines the different divisions to be made in the width dimension
                :param mode defines the underlying pooling mode to be used, can either be "max" or "avg"
                :returns (forward) a tensor vector with shape [batch x 1 x n],
                                                    where n: sum(filter_amount*level*level) for each level in levels
                                                    which is the concentration of multi-level pooling
                """
        super(SpatialPyramidPooling, self).__init__(levels, mode=mode)

    def forward(self, x):
        return self.spatial_pyramid_pool(x, self.levels, self.mode)

    def get_output_size(self, filters):
        """
                Calculates the output shape given a filter_amount: sum(filter_amount*level*level) for each level in levels
                Can be used to x.view(-1, spp.get_output_size(filter_amount)) for the fully-connected layers
                :param filters: the amount of filter of output fed into the spatial pyramid pooling
                :return: sum(filter_amount*level*level)
        """
        out = 0
        for level in self.levels:
            out += filters * level * level
        return out


class Agent(nn.Module):
    def __init__(self, n_channels, spp_layers):
        super(Agent, self).__init__()
        self.encoder = nn.Sequential(
            Transpose((0, 3, 1, 2)),
            layer_init(nn.Conv2d(n_channels, 32, kernel_size=3, padding=1)),
            nn.MaxPool2d(3, stride=2, padding=1),
            nn.ReLU(),
            layer_init(nn.Conv2d(32, 64, kernel_size=3, padding=1)),
            nn.MaxPool2d(3, stride=2, padding=1),
            nn.ReLU(),
        )

        self.actor = nn.Sequential(
            layer_init(nn.ConvTranspose2d(64, 32, 3, stride=2, padding=1, output_padding=1)),
            nn.ReLU(),
            layer_init(nn.ConvTranspose2d(32, 78, 3, stride=2, padding=1, output_padding=1)),
            Transpose((0, 2, 3, 1)),
        )

        spp_output_size = sum([layer*layer for layer in spp_layers])
        self.critic = nn.Sequential(
            SpatialPyramidPooling(spp_layers),
            layer_init(nn.Linear(64*(spp_output_size), 128)),
            nn.ReLU(),
            layer_init(nn.Linear(128, 1), std=1),
        )
        self.register_buffer("mask_value", torch.tensor(-1e8))

    def get_action_and_value(self, x, action=None, invalid_action_masks=None, envs=None, device=None):
        hidden = self.encoder(x)
        logits = self.actor(hidden)
        grid_logits = logits.reshape(-1, envs.action_plane_space.nvec.sum())
        split_logits = torch.split(grid_logits, envs.action_plane_space.nvec.tolist(), dim=1)

        if action is None:
            invalid_action_masks = invalid_action_masks.view(-1, invalid_action_masks.shape[-1])
            split_invalid_action_masks = torch.split(invalid_action_masks, envs.action_plane_space.nvec.tolist(), dim=1)
            multi_categoricals = [
                CategoricalMasked(logits=logits, masks=iam, mask_value=self.mask_value)
                for (logits, iam) in zip(split_logits, split_invalid_action_masks)
            ]
            action = torch.stack([categorical.sample() for categorical in multi_categoricals])
        else:
            invalid_action_masks = invalid_action_masks.view(-1, invalid_action_masks.shape[-1])
            action = action.view(-1, action.shape[-1]).T
            split_invalid_action_masks = torch.split(invalid_action_masks, envs.action_plane_space.nvec.tolist(), dim=1)
            multi_categoricals = [
                CategoricalMasked(logits=logits, masks=iam, mask_value=self.mask_value)
                for (logits, iam) in zip(split_logits, split_invalid_action_masks)
            ]
        h, w, _ = envs.observation_space.shape
        mapsize = h * w
        logprob = torch.stack([categorical.log_prob(a) for a, categorical in zip(action, multi_categoricals)])
        entropy = torch.stack([categorical.entropy() for categorical in multi_categoricals])
        num_predicted_parameters = len(envs.action_plane_space.nvec)
        logprob = logprob.T.view(-1, mapsize, num_predicted_parameters)
        entropy = entropy.T.view(-1, mapsize, num_predicted_parameters)
        action = action.T.view(-1, mapsize, num_predicted_parameters)
        return action, logprob.sum(1).sum(1), entropy.sum(1).sum(1), invalid_action_masks, self.critic(hidden)

    def get_value(self, x):
        return self.critic(self.encoder(x))


def run_evaluation(model_path: str, output_path: str, eval_maps: List[str]):
    args = [
        "python",
        "league.py",
        "--evals",
        model_path,
        "--update-db",
        "false",
        "--cuda",
        "false",
        "--output-path",
        output_path,
        "--model-type",
        "ppo_gridnet_spp",
        "--maps",
        *eval_maps,
    ]
    fd = subprocess.Popen(args)
    print(f"Evaluating {model_path}")
    return_code = fd.wait()
    assert return_code == 0
    return (model_path, output_path)


class TrueskillWriter:
    def __init__(self, prod_mode, writer, league_path: str, league_step_path: str):
        self.prod_mode = prod_mode
        self.writer = writer
        self.trueskill_df = pd.read_csv(league_path)
        self.trueskill_step_df = pd.read_csv(league_step_path)
        self.trueskill_step_df["type"] = self.trueskill_step_df["name"]
        self.trueskill_step_df["step"] = 0
        # xxx(okachaiev): not sure we need this copy
        self.preset_trueskill_step_df = self.trueskill_step_df.copy()

    def on_evaluation_done(self, future):
        if future.cancelled():
            return
        model_path, output_path = future.result()
        league = pd.read_csv(output_path, index_col="name")
        assert model_path in league.index
        model_global_step = int(model_path.split("/")[-1][:-3])
        self.writer.add_scalar("charts/trueskill", league.loc[model_path]["trueskill"], model_global_step)
        print(f"global_step={model_global_step}, trueskill={league.loc[model_path]['trueskill']}")

        # table visualization logic
        if self.prod_mode:
            trueskill_data = {
                "name": league.loc[model_path].name,
                "mu": league.loc[model_path]["mu"],
                "sigma": league.loc[model_path]["sigma"],
                "trueskill": league.loc[model_path]["trueskill"],
            }
            self.trueskill_df = self.trueskill_df.append(trueskill_data, ignore_index=True)
            wandb.log({"trueskill": wandb.Table(dataframe=self.trueskill_df)})
            trueskill_data["type"] = "training"
            trueskill_data["step"] = model_global_step
            self.trueskill_step_df = self.trueskill_step_df.append(trueskill_data, ignore_index=True)
            preset_trueskill_step_df_clone = self.preset_trueskill_step_df.copy()
            preset_trueskill_step_df_clone["step"] = model_global_step
            self.trueskill_step_df = self.trueskill_step_df.append(preset_trueskill_step_df_clone, ignore_index=True)
            wandb.log({"trueskill_step": wandb.Table(dataframe=self.trueskill_step_df)})


if __name__ == "__main__":
    args = parse_args()

    print(f"Save frequency: {args.save_frequency}")

    # TRY NOT TO MODIFY: setup the environment
    experiment_name = f"{args.gym_id}__{args.exp_name}__{args.seed}__{int(time.time())}"
    if args.prod_mode:
        import wandb

        run = wandb.init(
            project=args.wandb_project_name,
            entity=args.wandb_entity,
            # sync_tensorboard=True,
            config=vars(args),
            name=experiment_name,
            monitor_gym=True,
            save_code=True,
        )
        wandb.tensorboard.patch(save=False)
    writer = SummaryWriter(f"runs/{experiment_name}")
    writer.add_text(
        "hyperparameters", "|param|value|\n|-|-|\n%s" % ("\n".join([f"|{key}|{value}|" for key, value in vars(args).items()]))
    )

    # TRY NOT TO MODIFY: seeding
    device = torch.device("cuda" if torch.cuda.is_available() and args.cuda else "cpu")

    print(f"Device: {device}")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.backends.cudnn.deterministic = args.torch_deterministic

    N_CHANNELS = 27
    agent = Agent(N_CHANNELS, args.spp_layers).to(device)
    optimizer = optim.Adam(agent.parameters(), lr=args.learning_rate, eps=1e-5)
    if args.anneal_lr:
        # https://github.com/openai/baselines/blob/ea25b9e8b234e6ee1bca43083f8f3cf974143998/baselines/ppo2/defaults.py#L20
        lr = lambda f: f * args.learning_rate

    print("Model's state_dict:")
    for param_tensor in agent.state_dict():
        print(param_tensor, "\t", agent.state_dict()[param_tensor].size())
    total_params = sum([param.nelement() for param in agent.parameters()])
    print("Model's total parameters:", total_params)

    eval_executor = None
    if args.max_eval_workers > 0:
        from concurrent.futures import ThreadPoolExecutor

        eval_executor = ThreadPoolExecutor(max_workers=args.max_eval_workers, thread_name_prefix="league-eval-")


    global_step = 0
    if args.prod_mode:
        table = wandb.Table(columns=['step', 'map'])
    start_time = time.time()

    map_cycle = cycle(args.train_maps)

    def next_map(map_cycle):
        return next(map_cycle)

    for cycle_n in range(args.total_cycles*len(args.train_maps)):
        writer.add_scalar("charts/cycle", cycle_n, global_step)
        if args.random_maps:
            rts_map = random.choice(args.train_maps)
        else:
            rts_map = next_map(map_cycle)
        if args.prod_mode:
            table.add_data(global_step, rts_map)
        envs = MicroRTSGridModeVecEnv(
            num_selfplay_envs=args.num_selfplay_envs,
            num_bot_envs=args.num_bot_envs,
            partial_obs=args.partial_obs,
            max_steps=2000,
            render_theme=2,
            ai2s=[microrts_ai.coacAI for _ in range(args.num_bot_envs - 6)]
            + [microrts_ai.randomBiasedAI for _ in range(min(args.num_bot_envs, 2))]
            + [microrts_ai.lightRushAI for _ in range(min(args.num_bot_envs, 2))]
            + [microrts_ai.workerRushAI for _ in range(min(args.num_bot_envs, 2))],
            map_paths=[rts_map],
            reward_weight=np.array([10.0, 1.0, 1.0, 0.2, 1.0, 4.0]),
            cycle_maps=[rts_map],
        )
        envs = MicroRTSStatsRecorder(envs, args.gamma)
        envs = VecMonitor(envs)
        if args.capture_video:
            envs = VecVideoRecorder(
                envs, f"videos/{experiment_name}", record_video_trigger=lambda x: x % 100000 == 0, video_length=2000
            )
        assert isinstance(envs.action_space, MultiDiscrete), "only MultiDiscrete action space is supported"

        # ALGO Logic: Storage for epoch data
        h, w, _ = envs.observation_space.shape
        mapsize = h * w
        action_space_shape = (mapsize, len(envs.action_plane_space.nvec))
        invalid_action_shape = (mapsize, envs.action_plane_space.nvec.sum())

        obs = torch.zeros((args.num_steps, args.num_envs) + envs.observation_space.shape).to(device)
        actions = torch.zeros((args.num_steps, args.num_envs) + action_space_shape).to(device)
        logprobs = torch.zeros((args.num_steps, args.num_envs)).to(device)
        rewards = torch.zeros((args.num_steps, args.num_envs)).to(device)
        dones = torch.zeros((args.num_steps, args.num_envs)).to(device)
        values = torch.zeros((args.num_steps, args.num_envs)).to(device)
        invalid_action_masks = torch.zeros((args.num_steps, args.num_envs) + invalid_action_shape).to(device)

        # Note how `next_obs` and `next_done` are used; their usage is equivalent to
        # https://github.com/ikostrikov/pytorch-a2c-ppo-acktr-gail/blob/84a7582477fb0d5c82ad6d850fe476829dddd2e1/a2c_ppo_acktr/storage.py#L60
        next_obs = torch.Tensor(envs.reset()).to(device)
        next_done = torch.zeros(args.num_envs).to(device)

        # CRASH AND RESUME LOGIC:

        if args.prod_mode and wandb.run.resumed:
            starting_update = run.summary.get("charts/update") + 1
            global_step = starting_update * args.batch_size
            api = wandb.Api()
            run = api.run(f"{run.entity}/{run.project}/{run.id}")
            model = run.file("agent.pt")
            model.download(f"models/{experiment_name}/")
            agent.load_state_dict(torch.load(f"models/{experiment_name}/agent.pt", map_location=device))
            agent.eval()
            print(f"resumed at update {starting_update}")

        # EVALUATION LOGIC:
        trueskill_writer = TrueskillWriter(
            args.prod_mode, writer, "gym-microrts-static-files/league.csv", "gym-microrts-static-files/league.csv"
        )

        starting_update = 1 + (cycle_n * args.updates_per_map)

        for update in range(starting_update, (cycle_n + 1) * args.updates_per_map + 1):
            # Annealing the rate if instructed to do so.
            if args.anneal_lr:
                frac = 1.0 - (update - 1.0) / args.num_updates
                lrnow = lr(frac)
                optimizer.param_groups[0]["lr"] = lrnow

            # TRY NOT TO MODIFY: prepare the execution of the game.
            for step in range(0, args.num_steps):
                # envs.render()
                global_step += 1 * args.num_envs
                obs[step] = next_obs
                dones[step] = next_done
                # ALGO LOGIC: put action logic here
                with torch.no_grad():
                    invalid_action_masks[step] = torch.tensor(envs.get_action_mask()).to(device)
                    action, logproba, _, _, vs = agent.get_action_and_value(
                        next_obs, envs=envs, invalid_action_masks=invalid_action_masks[step], device=device
                    )
                    values[step] = vs.flatten()

                actions[step] = action
                logprobs[step] = logproba
                try:
                    next_obs, rs, ds, infos = envs.step(action.cpu().numpy().reshape(envs.num_envs, -1))
                    next_obs = torch.Tensor(next_obs).to(device)
                except Exception as e:
                    e.printStackTrace()
                    raise
                rewards[step], next_done = torch.Tensor(rs).to(device), torch.Tensor(ds).to(device)

                for info in infos:
                    if "episode" in info.keys():
                        print(f"global_step={global_step}, episodic_return={info['episode']['r']}")
                        writer.add_scalar("charts/episodic_return", info["episode"]["r"], global_step)
                        writer.add_scalar("charts/episodic_length", info["episode"]["l"], global_step)
                        for key in info["microrts_stats"]:
                            writer.add_scalar(f"charts/episodic_return/{key}", info["microrts_stats"][key], global_step)
                        break

            # bootstrap reward if not done. reached the batch limit
            with torch.no_grad():
                last_value = agent.get_value(next_obs).reshape(1, -1)
                if args.gae:
                    advantages = torch.zeros_like(rewards).to(device)
                    lastgaelam = 0
                    for t in reversed(range(args.num_steps)):
                        if t == args.num_steps - 1:
                            nextnonterminal = 1.0 - next_done
                            nextvalues = last_value
                        else:
                            nextnonterminal = 1.0 - dones[t + 1]
                            nextvalues = values[t + 1]
                        delta = rewards[t] + args.gamma * nextvalues * nextnonterminal - values[t]
                        advantages[t] = lastgaelam = delta + args.gamma * args.gae_lambda * nextnonterminal * lastgaelam
                    returns = advantages + values
                else:
                    returns = torch.zeros_like(rewards).to(device)
                    for t in reversed(range(args.num_steps)):
                        if t == args.num_steps - 1:
                            nextnonterminal = 1.0 - next_done
                            next_return = last_value
                        else:
                            nextnonterminal = 1.0 - dones[t + 1]
                            next_return = returns[t + 1]
                        returns[t] = rewards[t] + args.gamma * nextnonterminal * next_return
                    advantages = returns - values

            # flatten the batch
            b_obs = obs.reshape((-1,) + envs.observation_space.shape)
            b_logprobs = logprobs.reshape(-1)
            b_actions = actions.reshape((-1,) + action_space_shape)
            b_advantages = advantages.reshape(-1)
            b_returns = returns.reshape(-1)
            b_values = values.reshape(-1)
            b_invalid_action_masks = invalid_action_masks.reshape((-1,) + invalid_action_shape)

            # Optimizing the policy and value network
            inds = np.arange(
                args.batch_size,
            )
            for i_epoch_pi in range(args.update_epochs):
                np.random.shuffle(inds)
                for start in range(0, args.batch_size, args.minibatch_size):
                    end = start + args.minibatch_size
                    minibatch_ind = inds[start:end]
                    mb_advantages = b_advantages[minibatch_ind]
                    if args.norm_adv:
                        mb_advantages = (mb_advantages - mb_advantages.mean()) / (mb_advantages.std() + 1e-8)
                    _, newlogproba, entropy, _, new_values = agent.get_action_and_value(
                        b_obs[minibatch_ind], b_actions.long()[minibatch_ind], b_invalid_action_masks[minibatch_ind], envs, device
                    )
                    ratio = (newlogproba - b_logprobs[minibatch_ind]).exp()

                    # Stats
                    approx_kl = (b_logprobs[minibatch_ind] - newlogproba).mean()

                    # Policy loss
                    pg_loss1 = -mb_advantages * ratio
                    pg_loss2 = -mb_advantages * torch.clamp(ratio, 1 - args.clip_coef, 1 + args.clip_coef)
                    pg_loss = torch.max(pg_loss1, pg_loss2).mean()
                    entropy_loss = entropy.mean()

                    # Value loss
                    new_values = new_values.view(-1)
                    if args.clip_vloss:
                        v_loss_unclipped = (new_values - b_returns[minibatch_ind]) ** 2
                        v_clipped = b_values[minibatch_ind] + torch.clamp(
                            new_values - b_values[minibatch_ind], -args.clip_coef, args.clip_coef
                        )
                        v_loss_clipped = (v_clipped - b_returns[minibatch_ind]) ** 2
                        v_loss_max = torch.max(v_loss_unclipped, v_loss_clipped)
                        v_loss = 0.5 * v_loss_max.mean()
                    else:
                        v_loss = 0.5 * ((new_values - b_returns[minibatch_ind]) ** 2)

                    loss = pg_loss - args.ent_coef * entropy_loss + v_loss * args.vf_coef

                    optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                    optimizer.step()

            if (update - 1) % args.save_frequency == 0:
                if not os.path.exists(f"models/{experiment_name}"):
                    os.makedirs(f"models/{experiment_name}")
                torch.save(agent.state_dict(), f"models/{experiment_name}/agent.pt")
                torch.save(agent.state_dict(), f"models/{experiment_name}/{global_step}.pt")
                if args.prod_mode:
                    wandb.save(f"models/{experiment_name}/agent.pt", base_path=f"models/{experiment_name}", policy="now")
                if eval_executor is not None:
                    future = eval_executor.submit(
                        run_evaluation,
                        f"models/{experiment_name}/{global_step}.pt",
                        f"runs/{experiment_name}/{global_step}.csv",
                        args.eval_maps,
                    )
                    print(f"Queued models/{experiment_name}/{global_step}.pt")
                    future.add_done_callback(trueskill_writer.on_evaluation_done)

            # TRY NOT TO MODIFY: record rewards for plotting purposes
            writer.add_scalar("charts/learning_rate", optimizer.param_groups[0]["lr"], global_step)
            writer.add_scalar("charts/update", update, global_step)
            writer.add_scalar("losses/value_loss", v_loss.detach().item(), global_step)
            writer.add_scalar("losses/policy_loss", pg_loss.detach().item(), global_step)
            writer.add_scalar("losses/entropy", entropy.detach().mean().item(), global_step)
            writer.add_scalar("losses/approx_kl", approx_kl.detach().item(), global_step)
            if args.kle_stop or args.kle_rollback:
                writer.add_scalar("debug/pg_stop_iter", i_epoch_pi, global_step)
            writer.add_scalar("charts/sps", int(global_step / (time.time() - start_time)), global_step)
            print("SPS:", int(global_step / (time.time() - start_time)))


    # EVALUATION

    for map_id in args.eval_maps:
        for adversary in ["coacAI", "randomBiasedAI", "lightRushAI", "workerRushAI"]:
            if adversary == "coacAI":
                adv = microrts_ai.coacAI
            elif adversary == "randomBiasedAI":
                adv = microrts_ai.randomBiasedAI
            elif adversary == "lightRushAI":
                adv = microrts_ai.lightRushAI
            elif adversary == "workerRushAI":
                adv = microrts_ai.workerRushAI
            else:
                adv = None
                
            envs = MicroRTSGridModeVecEnv(
                num_selfplay_envs=0,
                num_bot_envs=args.num_bot_envs,
                partial_obs=args.partial_obs,
                max_steps=2000,
                render_theme=2,
                ai2s=[adv for _ in range(args.num_bot_envs)],
                map_paths=[map_id],
                reward_weight=np.array([10.0, 1.0, 1.0, 0.2, 1.0, 4.0]),
                cycle_maps=[map_id],
            )
            envs = MicroRTSStatsRecorder(envs, args.gamma)
            envs = VecMonitor(envs)
            if args.capture_video:
                envs = VecVideoRecorder(
                    envs, f"videos/{experiment_name}", record_video_trigger=lambda x: x % 100000 == 0, video_length=2000
                )
            assert isinstance(envs.action_space, MultiDiscrete), "only MultiDiscrete action space is supported"

            game_results = []

            NUM_MATCHES = 100
            next_obs = torch.Tensor(envs.reset()).to(device)
            while len(game_results) < NUM_MATCHES:
                # ALGO LOGIC: put action logic here
                with torch.no_grad():
                    mask = torch.tensor(envs.get_action_mask()).to(device)
                    action, _, _, _, _ = agent.get_action_and_value(
                        next_obs, envs=envs, invalid_action_masks=mask, device=device
                    )
                try:
                    next_obs, rs, ds, infos = envs.step(action.cpu().numpy().reshape(envs.num_envs, -1))
                    next_obs = torch.Tensor(next_obs).to(device)
                except Exception as e:
                    e.printStackTrace()
                    raise

                for idx, info in enumerate(infos):
                    if "episode" in info.keys():
                        game_results += [info["microrts_stats"]["WinLossRewardFunction"]]
                        if len(game_results) >= NUM_MATCHES:
                            break

            writer.add_scalar(f"evaluation/{map_id}/{adversary}/score", mean(game_results), global_step)
            writer.add_scalar(f"evaluation/{map_id}/{adversary}/wins", game_results.count(1), global_step)
            writer.add_scalar(f"evaluation/{map_id}/{adversary}/draws", game_results.count(0), global_step)
            writer.add_scalar(f"evaluation/{map_id}/{adversary}/losses", game_results.count(-1), global_step)

    if args.prod_mode:
        run.log({'maps': table})
    if eval_executor is not None:
        # shutdown pool of threads but make sure we finished scheduled evaluations
        eval_executor.shutdown(wait=True, cancel_futures=False)
    envs.close()
    writer.close()
