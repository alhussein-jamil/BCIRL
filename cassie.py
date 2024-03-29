import logging as log
import os
from copy import deepcopy

import gymnasium as gym
import mujoco as m
import numpy as np
import torch
from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
from gymnasium.spaces import Box

import yaml
import constants as c
import functions as f

log.basicConfig(level=log.DEBUG)


class CassieEnv(MujocoEnv):
    metadata = {
        "render_modes": [
            "human",
            "rgb_array",
            "depth_array",
        ],
        "render_fps": 100,
    }

    def __init__(self, config):
        DIRPATH = os.path.dirname(os.path.realpath(__file__))
        config = yaml.safe_load(open( "dict_config.yaml", "r"))["env_config"]
        self._terminate_when_unhealthy = config.get("terminate_when_unhealthy", True)
        self._healthy_pelvis_z_range = config.get("pelvis_height", (0.60, 1.5))
        self._healthy_feet_distance_x = config.get("feet_distance_x", (0.0, 1.0))
        self._healthy_feet_distance_y = config.get("feet_distance_y",(0.0, 0.6))
        self._healthy_feet_distance_z = config.get("feet_distance_z", (0.0, 0.5))
        self._healthy_dis_to_pelvis = config.get("feet_pelvis_height", 0.3)
        self._healthy_feet_height = config.get("feet_height", (0.0, 0.4))
        self._max_steps = config.get("max_simulation_steps", 400)
        self.steps_per_cycle = config.get("steps_per_cycle", 30)
        self.a_swing = config.get("a_swing", 0)
        self.a_stance = config.get("a_stance", 0.5)
        self.b_swing = config.get("b_swing", 0.5)
        self.b_stance = config.get("b_stance", 1)
        self.kappa = config.get("kappa", 25)
        self.x_cmd_vel = config.get("x_cmd_vel", 0.8)
        self.y_cmd_vel = config.get("y_cmd_vel", 0)
        self.z_cmd_vel = config.get("z_cmd_vel",0 )

        self.action_space = gym.spaces.Box(
            np.float32(c.low_action), np.float32(c.high_action)
        )

        self._reset_noise_scale = config.get("reset_noise_scale", 1e-2)

        self.phi, self.steps, self.gamma_modified = 0, 0, 1
        self.previous_action = torch.zeros(10)
        self.gamma = config.get("gamma", 0.99)

        self.observation_space = Box(
            low=-1.2,
            high=1.2,
            shape=(25,),
        )

        MujocoEnv.__init__(
            self,
            config.get(
                "model_path",
                DIRPATH + "/cassie-mujoco-sim-master/model/cassie.xml",
            ),
            20,
            render_mode=config.get("render_mode", None),
            observation_space=self.observation_space
        )
        self.render_mode = "rgb_array"

    @property
    def healthy_reward(self):
        return (
            float(self.is_healthy or self._terminate_when_unhealthy)
            * self._healthy_reward
        )

    @property
    def is_healthy(self):
        min_z, max_z = self._healthy_pelvis_z_range


        self.isdone = "not done"

        if not min_z < self.data.xpos[c.PELVIS, 2] < max_z:
            self.isdone = "Pelvis not in range"

        if not self.steps <= self._max_steps:
            self.isdone = "Max steps reached"

        if not self._healthy_feet_distance_x[0] < abs(self.data.xpos[c.LEFT_FOOT, 0] - self.data.xpos[c.RIGHT_FOOT, 0]) < self._healthy_feet_distance_x[1]:
            self.isdone = "Feet distance out of range along x-axis"
       
        if not self._healthy_feet_distance_y[0] < abs(self.data.xpos[c.LEFT_FOOT, 1] - self.data.xpos[c.RIGHT_FOOT, 1]) < self._healthy_feet_distance_y[1]:
            self.isdone = "Feet distance out of range along y-axis"
        
        if not self._healthy_feet_distance_z[0] < abs(self.data.xpos[c.LEFT_FOOT, 2] - self.data.xpos[c.RIGHT_FOOT, 2]) < self._healthy_feet_distance_z[1]:
            self.isdone = "Feet distance out of range along z-axis"

        if self.contact and self.data.xpos[c.LEFT_FOOT, 2] >= self._healthy_feet_height and self.data.xpos[c.RIGHT_FOOT, 2] >= self._healthy_feet_height:
            self.isdone = "Both Feet not on the ground"

        if not self._healthy_dis_to_pelvis < self.data.xpos[c.PELVIS, 2] - self.data.xpos[c.LEFT_FOOT, 2]:
            self.isdone = "Left foot too close to pelvis"

        if not self._healthy_dis_to_pelvis < self.data.xpos[c.PELVIS, 2] - self.data.xpos[c.RIGHT_FOOT, 2]:
            self.isdone = "Right foot too close to pelvis"
        
        if self.data.xpos[c.LEFT_FOOT, 1] > self.data.xpos[c.RIGHT_FOOT, 1]:
            self.isdone = "Feet Crossed"


        return self.isdone == "not done"

    @property
    def terminated(self):
        terminated = (
            (not self.is_healthy)
            if (self._terminate_when_unhealthy)  # or self.steps > c.MAX_STEPS)
            else False
        )
        return terminated

    def _get_obs(self):
        p = np.array(
            [np.sin((2 * np.pi * (self.phi))), np.cos((2 * np.pi * (self.phi)))]
        )
        temp = []
        # normalize the sensor data using sensor_ranges
        # self.data.sensor('pelvis-orientation').data
        i = 0
        for key in c.sensor_ranges.keys():
            for x in self.data.sensor(key).data:
                temp.append(
                    (x - c.obs_ranges[0][i]) / (c.obs_ranges[1][i] - c.obs_ranges[0][i])
                )
                # temp.append(x)
                i += 1
        self.obs = np.clip(
            np.concatenate([temp, p]),
            self.observation_space.low,
            self.observation_space.high,
        )
        # getting the read positions of the sensors and concatenate the lists
        return self.obs



    def _get_symmetric_obs(self):
        obs = self._get_obs()
        symmetric_obs = deepcopy(obs)
        symmetric_obs[0:8] = obs[8:16]
        symmetric_obs[8:16] = obs[0:8]
        symmetric_obs[17] = -obs[17]
        symmetric_obs[19] = -obs[19]
        symmetric_obs[21] = -obs[21]
        symmetric_obs[24] = -obs[24]
        symmetric_obs[29] = obs[30]
        symmetric_obs[30] = obs[29]

        return symmetric_obs

    # computes the reward
    def compute_reward(self, action):
        # Extract some proxies
        qpos = self.data.qpos.flat.copy()
        qvel = self.data.qvel.flat.copy()

        qpos = qpos[c.pos_index]
        qvel = qvel[c.vel_index]

        # # Feet Contact Forces
        # contact_force_right_foot = np.zeros(6)
        # m.mj_contactForce(self.model, self.data, 0, contact_force_right_foot)
        # contact_force_left_foot = np.zeros(6)
        # m.mj_contactForce(self.model, self.data, 1, contact_force_left_foot)

        contacts = [contact.geom2 for contact in self.data.contact]
        contact_force_left_foot = np.zeros(6)
        contact_force_right_foot = np.zeros(6)
        if c.left_foot_force_idx in contacts:
            m.mj_contactForce(
                self.model,
                self.data,
                contacts.index(c.left_foot_force_idx),
                contact_force_left_foot,
            )
        if c.right_foot_force_idx in contacts:
            m.mj_contactForce(
                self.model,
                self.data,
                contacts.index(c.right_foot_force_idx),
                contact_force_right_foot,
            )

        # check if cassie hit the ground with feet
        if (
            self.data.xpos[c.LEFT_FOOT, 2] < 0.12
            or self.data.xpos[c.RIGHT_FOOT, 2] < 0.12
        ):
            self.contact = True

        # Some metrics to be used in the reward function
        q_vx = 1 - np.exp(
            c.multiplicators["q_vx"]
            * np.linalg.norm(np.array([qvel[0]]) - np.array([self.x_cmd_vel])) ** 2
        )
        q_vy = 1 - np.exp(
            c.multiplicators["q_vy"]
            * np.linalg.norm(np.array([qvel[1]]) - np.array([self.y_cmd_vel])) ** 2
        )
        q_vz = 1 - np.exp(
            c.multiplicators["q_vz"]
            * np.linalg.norm(np.array([qvel[2]]) - np.array([self.z_cmd_vel])) ** 2
        )

        q_left_frc = 1.0 - np.exp(
            c.multiplicators["q_frc"] * np.linalg.norm(contact_force_left_foot) ** 2
        )
        q_right_frc = 1.0 - np.exp(
            c.multiplicators["q_frc"] * np.linalg.norm(contact_force_right_foot) ** 2
        )
        q_left_spd = 1.0 - np.exp(
            c.multiplicators["q_spd"] * np.linalg.norm(qvel[12]) ** 2
        )
        q_right_spd = 1.0 - np.exp(
            c.multiplicators["q_spd"] * np.linalg.norm(qvel[19]) ** 2
        )
        q_action_diff = 1 - np.exp(
            c.multiplicators["q_action"]
            * float(
                f.action_dist(
                    torch.tensor(action).clone().detach().reshape(1, -1),
                    torch.tensor(self.previous_action).clone().detach().reshape(1, -1),
                )
            )
        )
        q_orientation = 1 - np.exp(
            c.multiplicators["q_orientation"]
            * (
                1
                - (
                    (self.data.sensor("pelvis-orientation").data.T)
                    @ (c.FORWARD_QUARTERNIONS)
                )
                ** 2
            )
        )
        q_torque = 1 - np.exp(c.multiplicators["q_torque"] * np.linalg.norm(action))
        q_pelvis_acc = 1 - np.exp(
            c.multiplicators["q_pelvis_acc"]
            * (np.linalg.norm(self.data.sensor("pelvis-angular-velocity").data))
        )

        cycle_steps = float(self.steps % self.steps_per_cycle) / self.steps_per_cycle
        phase_left = (
            1 if 0.75 > cycle_steps >= 0.5 else -1 if 1 > cycle_steps >= 0.75 else 0
        )
        phase_right = (
            1 if 0.25 > cycle_steps >= 0 else -1 if 0.5 > cycle_steps >= 0.25 else 0
        )

        q_phase_left = 1.0 - np.exp(
            c.multiplicators["q_marche_distance"]
            * np.clip(
                phase_left
                * (
                    0.2
                    + self.data.xpos[c.LEFT_FOOT][0]
                    - self.data.xpos[c.RIGHT_FOOT][0]
                ),
                0,
                np.inf,
            )
        )
        q_phase_right = 1.0 - np.exp(
            c.multiplicators["q_marche_distance"]
            * np.clip(
                phase_right
                * (
                    0.2
                    + self.data.xpos[c.RIGHT_FOOT][0]
                    - self.data.xpos[c.LEFT_FOOT][0]
                ),
                0,
                np.inf,
            )
        )

        q_feet_orientation_left = 1 - np.exp(
            c.multiplicators["q_feet_orientation"]
            * np.abs(
                self.data.sensordata[c.LEFT_FOOT_JOINT] - c.target_feet_orientation
            )
        )
        q_feet_orientation_right = 1 - np.exp(
            c.multiplicators["q_feet_orientation"]
            * np.abs(
                self.data.sensordata[c.RIGHT_FOOT_JOINT] - c.target_feet_orientation
            )
        )

        self.exponents = {
            "q_vx": np.linalg.norm(np.array([qvel[0]]) - np.array([self.x_cmd_vel])) ** 2,
            "q_vy": np.linalg.norm(np.array([qvel[1]]) - np.array([self.y_cmd_vel])) ** 2,
            "q_vz": np.linalg.norm(np.array([qvel[2]]) - np.array([self.z_cmd_vel])) ** 2,
            "q_left_frc": np.linalg.norm(contact_force_left_foot) ** 2,
            "q_right_frc": np.linalg.norm(contact_force_right_foot) ** 2,
            "q_left_spd": np.linalg.norm(qvel[12]) ** 2,
            "q_right_spd": np.linalg.norm(qvel[19]) ** 2,
            "q_action_diff": float(
                f.action_dist(
                    torch.tensor(action).clone().detach().reshape(1, -1),
                    torch.tensor(self.previous_action).clone().detach().reshape(1, -1),
                )
            ),
            "q_orientation": (
                1
                - (
                    (self.data.sensor("pelvis-orientation").data.T)
                    @ (c.FORWARD_QUARTERNIONS)
                )
                ** 2
            ),
            "q_torque": np.linalg.norm(action),
            "q_pelvis_acc": np.linalg.norm(
                self.data.sensor("pelvis-angular-velocity").data
            )
            + np.linalg.norm(
                self.data.sensor("pelvis-linear-acceleration").data
                - self.model.opt.gravity.data
            ),
            "feet distance": np.linalg.norm(
                self.data.xpos[c.LEFT_FOOT][0] - self.data.xpos[c.RIGHT_FOOT][0]
            ),
            "pelvis_height ": self.data.xpos[c.PELVIS, 2],
            "oriantation_right_foot": np.abs(
                self.data.sensordata[c.RIGHT_FOOT_JOINT] - c.target_feet_orientation
            ),
            "oriantation_left_foot": np.abs(
                self.data.sensordata[c.LEFT_FOOT_JOINT] - c.target_feet_orientation
            ),
        }
        used_quantities = {
            "q_vx": q_vx,
            "q_vy": q_vy,
            "q_vz": q_vz,
            "q_left_frc": q_left_frc,
            "q_right_frc": q_right_frc,
            "q_left_spd": q_left_spd,
            "q_right_spd": q_right_spd,
            "q_action_diff": q_action_diff,
            "q_orientation": q_orientation,
            "q_torque": q_torque,
            "q_pelvis_acc": q_pelvis_acc,
            "q_phase_left": q_phase_left,
            "q_phase_right": q_phase_right,
            "q_feet_orientation_left": q_feet_orientation_left,
            "q_feet_orientation_right": q_feet_orientation_right,
        }

        self.used_quantities = used_quantities

        # Responsable for the swing and stance phase
        def i(phi, a, b):
            return f.von_mises_approx(a, b, self.kappa, phi)

        def i_swing_frc(phi):
            return i(phi, self.a_swing, self.b_swing)

        def i_swing_spd(phi):
            return i(phi, self.a_swing, self.b_swing)

        def i_stance_spd(phi):
            return i(phi, self.a_stance, self.b_stance)

        def i_stance_frc(phi):
            return i(phi, self.a_stance, self.b_stance)

        def c_frc(phi):
            return c.c_swing_frc * i_swing_frc(phi) + c.c_stance_frc * i_stance_frc(phi)

        def c_spd(phi):
            return c.c_swing_spd * i_swing_spd(phi) + c.c_stance_spd * i_stance_spd(phi)

        r_alternate = (-1.0 * q_phase_left - 1.0 * q_phase_right) / (1.0 + 1.0)

        r_cmd = (
            -1.0 * q_vx
            - 1.0 * q_vy
            - 1.0 * q_orientation
            - 0.5 * q_vz
            - 1.0 * q_feet_orientation_left
            - 1.0 * q_feet_orientation_right
        ) / (1.0 + 1.0 + 1.0 + 0.5 + 1.0 + 1.0)

        r_smooth = (-1.0 * q_action_diff - 1.0 * q_torque - 1.0 * q_pelvis_acc) / (
            1.0 + 1.0 + 1.0
        )
        # if(self.steps > 0):
        #     print((c_frc(self.phi + c.THETA_LEFT) - self.C["C_frc_left"])*c.STEPS_IN_CYCLE < -5 and  c_frc(self.phi + c.THETA_LEFT) < -0.8 )
        # if(c_frc(self.phi + c.THETA_LEFT)  < 0 ):
        #     print(self.C["C_frc_left"])
        #     if(self.C["C_frc_left"] != -1.0):
        #         print("left foot changed")
        # r_alt = c_frc(self.phi + c.THETA_LEFT) * relative_pos_left + c_frc(self.phi + c.THETA_RIGHT) * relative_pos_right
        # r_alt *= 10
        # r_alt = np.clip(r_alt, -1, 0)
        r_biped = 0
        r_biped += c_frc(self.phi + c.THETA_LEFT) * q_left_frc
        r_biped += c_frc(self.phi + c.THETA_RIGHT) * q_right_frc
        r_biped += c_spd(self.phi + c.THETA_LEFT) * q_left_spd
        r_biped += c_spd(self.phi + c.THETA_RIGHT) * q_right_spd

        r_biped /= 2.0

        reward = (4.0 * r_biped + 3.0 * r_cmd + 3.0 * r_alternate + 1.0 * r_smooth) / (
            4.0 + 3.0 + 3.0 + 1.0
        ) + 1.0  # ADD SOME EXTRA REWARD TO ENCOURAGE THE AGENT TO STAY ALIVE

        rewards = {
            "r_biped": r_biped,
            "r_cmd": r_cmd,
            "r_smooth": r_smooth,
            "r_alternate": r_alternate,
        }

        self.C = {
            "sin": self.obs[-2],
            "cos": self.obs[-1],
            "phase_right": phase_right,
            "phase_left": phase_left,
            "C_frc_left": c_frc(self.phi + c.THETA_LEFT),
            "C_frc_right": c_frc(self.phi + c.THETA_RIGHT),
            "C_spd_left": c_spd(self.phi + c.THETA_LEFT),
            "C_spd_right": c_spd(self.phi + c.THETA_RIGHT),
        }

        metrics = {
            "dis_x": self.data.geom_xpos[16, 0],
            "dis_y": self.data.geom_xpos[16, 1],
            "dis_z": self.data.geom_xpos[16, 2],
            "vel_x": self.data.qvel[0],
            "vel_y": self.data.qvel[1],
            "vel_z": self.data.qvel[2],
            "feet_distance_x": abs(
                self.data.xpos[c.LEFT_FOOT, 0] - self.data.xpos[c.RIGHT_FOOT, 0]
            ),
            "feet_distance_y": abs(
                self.data.xpos[c.LEFT_FOOT, 1] - self.data.xpos[c.RIGHT_FOOT, 1]
            ),
            "feet_distance_z": abs(
                self.data.xpos[c.LEFT_FOOT, 2] - self.data.xpos[c.RIGHT_FOOT, 2]
            ),
        }
        return reward, used_quantities, rewards, metrics

    # step in time
    def step(self, action):
        # clip the action to the ranges in action_space (done inside the config
        # that's why removed)
        # action = np.clip(action, self.action_space.low, self.action_space.high)

        self.do_simulation(action, self.frame_skip)

        m.mj_step(self.model, self.data)

        observation = self._get_obs()

        reward, used_quantities, rewards, metrics = self.compute_reward(action)

        terminated = self.terminated

        self.steps += 1
        self.phi += 1.0 / self.steps_per_cycle
        self.phi = self.phi % 1

        self.previous_action = action

        self.gamma_modified *= self.gamma
        info = {}
        info["custom_rewards"] = rewards
        info["custom_quantities"] = used_quantities

        info["custom_metrics"] = {
            "distance": self.data.qpos[0],
            "height": self.data.qpos[2],
        }

        info["other_metrics"] = metrics

        return observation, reward, terminated, info

    # resets the simulation
    def reset_model(self, seed=0):
        m.mj_inverse(self.model, self.data)
        noise_low = -self._reset_noise_scale
        noise_high = self._reset_noise_scale
        self.previous_action = np.zeros(10)
        self.phi = np.random.randint(0, self.steps_per_cycle) / self.steps_per_cycle
        self.phi = 0
        self.steps = 0
        self.contact = False
        # self.rewards = {"R_biped": 0, "R_cmd": 0, "R_smooth": 0}

        self.gamma_modified = 1
        qpos = self.init_qpos + self.np_random.uniform(
            low=noise_low, high=noise_high, size=self.model.nq
        )
        qvel = self.init_qvel + self.np_random.uniform(
            low=noise_low, high=noise_high, size=self.model.nv
        )
        self.set_state(qpos, qvel)

        observation = self._get_obs()
        return observation

