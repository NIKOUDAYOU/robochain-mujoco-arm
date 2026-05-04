import numpy as np
import os
from robopal.envs import RobotEnv
from robopal.robots.diana_med import DianaGrasp
from robopal.robots.panda import PandaGrasp
from robopal.robots.ur5e import UR5eGrasp
ASSET_DIR = os.path.join(os.path.dirname(__file__), '../assets')

def primitive(func, checker=None):
    """ primitive flag, no practical effect. """

    def primitive_wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return primitive_wrapper


class GraspingEnv(RobotEnv,PandaGrasp):
    def __init__(self,
                 robot=PandaGrasp,
                 render_mode='human',
                 control_freq=20,
                 gripper = 'PandaHand',
                 enable_camera_viewer=False,
                 controller='CARTIK',
                 is_interpolate=False,
                 ):
        super().__init__(
             robot=robot,
            render_mode=render_mode,
            control_freq=control_freq,
            controller=controller,
            is_interpolate=is_interpolate,
        )
        
        self.init_pos, self.init_rot = self.controller.forward_kinematics(self.robot.get_arm_qpos())
        self.action = self.init_pos
        self.end_name = {self.agents[0]: '0_eef'}
        def addasset(self):
            self.mjcf_generator.add_node_from_xml(ASSET_DIR + '/objects/cube/green_cube.xml')
        
    @primitive
    def reset_robot(self):
        print("i am reset")
        self.move(self.init_pos, self.init_rot)

    @primitive
    def get_obj_pose(self, obj_name):
     
        pos = self.mj_data.body(obj_name).xpos.copy()
        pos[2] -= 0.31
        quat = self.mj_data.body(obj_name).xquat.copy()
        return pos, quat

    @primitive
    def move(self, pos, quat):
        print("i am move now")
        def checkArriveState(state):
            current_pos, current_quat = self.get_current_pose()
            error = np.sum(np.abs(state[:3] - current_pos)) + np.sum(np.abs(state[3:] - current_quat))
            if error <= 0.02:
                return True
            return False

        while True:
            self.action = np.concatenate((pos, quat), axis=0)
            self.step(self.action)
            if checkArriveState(self.action):
                break

    @primitive
    def grab(self, obj_name):
        self.gripper_ctrl("open")
        obj_pos, obj_quat = self.get_obj_pose(obj_name)
        self.move(np.add(obj_pos, np.array([0, 0, 0.1])), obj_quat)
        self.move(obj_pos, obj_quat)
        self.gripper_ctrl("close")
        end_pos, end_quat = self.get_current_pose()
        self.move(np.add(end_pos, np.array([0, 0, 0.1])), end_quat)

    @primitive
    def gripper_ctrl(self, cmd: str):
        if cmd == "open":
            #self.mj_data.actuator("0_actuator1").ctrl = 20
            # block_pos = np.array([0.5,0,0.2])
            # for i in range(int(200)):
            #     env.step(block_pos)
            # for t in range(int(200)):
            #     env.robot.end['arm0'].close()
            #     env.step(block_pos)
            #     block_pos += np.array([0.0, 0.0, 0.29])    
            block_pos = np.array([0.5,0,0.2])
            
        elif cmd == "grip":
            action = np.array([0.4,0,0.3])
            for t in range(int(200)):
                env.step(action)
            for t in range(int(200)):
                env.robot.end['arm0'].close()
                env.step(action)
                action += np.array([0.0, 0.0, 0.29])    
                    
        elif cmd == "close":
            self.mj_data.actuator("0_actuator1").ctrl = -20
    @primitive
    def get_current_pose(self):
        return self.controller.forward_kinematics(self.robot.get_arm_qpos())


def make_env():
    env = GraspingEnv(
            render_mode="human",
            control_freq=100,
    )
    return env

if __name__ == "__main__":
    env = make_env()
    env.controller.reference = 'world'
    env.reset()
    
    print("current pos",env.get_current_pose())
    env.move(np.array([0.6, 0.6, 0.2]), np.array([1, 2, 0, 0]))
    env.close()
    
