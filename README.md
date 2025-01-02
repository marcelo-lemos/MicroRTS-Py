# Enhancing Deep Reinforcement Learning for Scale Flexibility in Real-Time Strategy Games

This repository contains the code and supplementary materials for the paper **Enhancing Deep Reinforcement Learning for Scale Flexibility in Real-Time Strategy Games**.

## Cite us
If you find this work useful in your research, please consider citing our paper:

```
@article{lemos2025enhancing,
  title={Enhancing deep reinforcement learning for scale flexibility in real-time strategy games},
  author={Lemos, Marcelo Luiz Harry Diniz and Tavares, Anderson Rocha and Marcolino, Leandro Soriano and Chaimowicz, Luiz and others},
  journal={Entertainment Computing},
  volume={52},
  pages={100843},
  year={2025},
  publisher={Elsevier}
}
```

## Table of Contents

- [Abstract](#abstract)
- [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Installation](#installation)
    - [Usage](#usage)
- [Reproducing Results](#reproducing-results)
- [Acknowledgment](#acknowledgment)

## Abstract
Real-time strategy (RTS) games present a unique challenge for AI agents due to the combination of several fundamental AI problems. While Deep Reinforcement Learning (DRL) has shown promise in the development of autonomous agents for the genre, existing architectures often struggle with games featuring maps of varying dimensions. This limitation hinders the agent’s ability to generalize its learned strategies across different scenarios. 

This paper proposes a novel approach that overcomes this problem by incorporating Spatial Pyramid Pooling (SPP) within a DRL framework. Leveraging the GridNet architecture’s encoder–decoder structure, the implementation integrates an SPP layer into the critic network of the Proximal Policy Optimization (PPO) algorithm. This SPP layer dynamically generates a standardized representation of the game state, regardless of the initial observation size. As a result, agents effectively adapt their decision-making process to any map configuration. 

Our evaluations highlight significant enhancements in model flexibility and efficiency in training agents for various RTS game scenarios, paving the way for more robust and adaptable AI agents capable of excelling in sequential decision problems with variable-size observations.

## Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:
* Python 3.8+
* [Poetry](https://python-poetry.org)
* Java 8.0+

### Installation

To set up the project, run the following commands:
```bash
$ git clone --recursive https://github.com/vwxyzjn/gym-microrts.git && \
cd gym-microrts
poetry install
python hello_world.py
```

### Usage

#### Running experiments

The script for running the experiments described in our paper is located at [experiments/ppo_gridnet_spp.py](experiments/ppo_gridnet_spp.py).

To train and test a model, execute:
```bash
python experiments/ppo_gridnet_spp.py
```
#### Customizing Parameters

You can customize various experiment parameters directly from the command line, including the maps used for training and evaluation, as well as the SPP layer size of the model. For example, to train the agent on an 8x8 map and test it on both 8x8 and 16x16 maps, use:

```bash
python experiments/ppo_gridnet_spp.py --train-maps maps/8x8/basesWorkers8x8.xml --eval-maps maps/8x8/basesWorkers8x8.xml maps/16x16/basesWorkers16x16.xml
```

For a full list of adjustable parameters, refer to the beginning of the script file.

## Reproducing Results

To reproduce our experiments, use the parameter settings specified for each experiment in our paper. Parameters not explicitly mentioned in the paper default to the values provided in the script.

## Acknowledgment

This repository was based on the [MicroRTS-Py repository by Farama-Foundation](https://github.com/Farama-Foundation/MicroRTS-Py).
