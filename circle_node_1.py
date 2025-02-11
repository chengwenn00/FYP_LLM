#! /usr/bin/env python

"""
 * File: offb_node.py
 * Stack and tested in Gazebo Classic 9 SITL
"""

import sys
import time
import rospy
from math import cos, cosh, pi, sin
import numpy as np

from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

current_state = State()

def state_cb(msg):
    global current_state
    current_state = msg

def generate_line(ini_obj_position):
	pos_traj = []
	cur_obj_position = ini_obj_position.copy()
	cur_obj_position[2] += 1.2
		#Takeoff and hover to wait for car
	# for i in range(0, 2):
	# 	cur_obj_position[0] += (0.3 * 0.002)
	#  	# print(cur_obj_position)
	# 	pos_traj.append(cur_obj_position.copy())
	#Takeoff and hover to wait for car
	for i in range(0, 2000):
		pos_traj.append(cur_obj_position.copy())

	#Move forward
	for i in range(0, 2500):
		cur_obj_position[0] += (0.2 * 0.004)
	 	# print(cur_obj_position)
		pos_traj.append(cur_obj_position.copy())

	#Hover
	for i in range(0, 400):

		pos_traj.append(pos_traj[2499])
	print (pos_traj)

	#Move backward
	for i in range(0, 2500):
		cur_obj_position[0] -= (0.2 * 0.004)
	 	# print(cur_obj_position)
		pos_traj.append(cur_obj_position.copy())

	#Hover
	for i in range(0, 400):

		pos_traj.append(pos_traj[4897])

	#Move forward
	for i in range(0, 2500):
		cur_obj_position[0] += (0.2 * 0.004)
	 	# print(cur_obj_position)
		pos_traj.append(cur_obj_position.copy())

	#Hover
	for i in range(0, 400):
		pos_traj.append(pos_traj[7295])
	print (pos_traj)

	#Move backward
	for i in range(0, 2500):
		cur_obj_position[1] -= (0.2 * 0.004)
	 	# print(cur_obj_position)
		pos_traj.append(cur_obj_position.copy())

	#Hover
	for i in range(0, 400):
		pos_traj.append(pos_traj[9693])

	return pos_traj

def generate_circle(ini_obj_position):
	pos_traj = []
	cur_obj_position = ini_obj_position.copy()
	cur_obj_position[2] += 1.2
	#Takeoff and hover to wait for car
	for i in range(0, 2000):
		pos_traj.append(cur_obj_position.copy())

	for i in range(0, 1500000):
		cur_obj_position[0] = ini_obj_position[0] + (1 * sin(0.002*i))  #Omega = 0.001
		cur_obj_position[1] = ini_obj_position[1] + (1 * cos(0.002*i)) -1
		pos_traj.append(cur_obj_position.copy())
	return pos_traj

def generate_s_trajectory(ini_obj_position):
	pos_traj = []
	cur_obj_position = ini_obj_position.copy()
	cur_obj_position[2] += 1.2

	#Takeoff and hover to wait for car
	for i in range(0, 2000):
		pos_traj.append(cur_obj_position.copy())

	sign = -1
	for i in range(0, 1001):
		cur_obj_position[1] = ini_obj_position[1] + (1 * sin(0.002*pi*i))
		if i % 1000 == 0:
			sign = -1*sign
		cur_obj_position[0] += 2.5*sign*(0.001)
		pos_traj.append(cur_obj_position.copy())

	for i in range(0, 500):
		pos_traj.append(cur_obj_position.copy())
	return pos_traj

if __name__ == "__main__":
    rospy.init_node("offb_node_py")

    state_sub = rospy.Subscriber("mavros/state", State, callback = state_cb)

    local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)

    rospy.wait_for_service("/mavros/cmd/arming")
    arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)

    rospy.wait_for_service("/mavros/set_mode")
    set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)


    # Setpoint publishing MUST be faster than 2Hz
    rate = rospy.Rate(50)

    # Wait for Flight Controller connection
    while(not rospy.is_shutdown() and not current_state.connected):
        rate.sleep()

    # Trajectory index
    index = 0

    pose = PoseStamped()

    pose.header.stamp = rospy.Time.now()
    pose.pose.position.x = 0
    pose.pose.position.y = 3
    pose.pose.position.z = 1

    # Send a few setpoints before starting
    for i in range(100):
        if(rospy.is_shutdown()):
            break

        local_pos_pub.publish(pose)
        rate.sleep()
        
    # Set the trajectory
    pos_traj = []
    ini_obj_position = [0.0, 3.0, 1.0]
    pos_traj = generate_circle(ini_obj_position)
    
    offb_set_mode = SetModeRequest()
    offb_set_mode.custom_mode = 'OFFBOARD'

    arm_cmd = CommandBoolRequest()
    arm_cmd.value = True

    last_req = rospy.Time.now()

    while(not rospy.is_shutdown()):
        if(current_state.mode != "OFFBOARD" and (rospy.Time.now() - last_req) > rospy.Duration(5.0)):
            if(set_mode_client.call(offb_set_mode).mode_sent == True):
                rospy.loginfo("OFFBOARD enabled")

            last_req = rospy.Time.now()
        else:
            if(not current_state.armed and (rospy.Time.now() - last_req) > rospy.Duration(5.0)):
                if(arming_client.call(arm_cmd).success == True):
                    rospy.loginfo("Vehicle armed")

                last_req = rospy.Time.now()

        if(pos_traj is not None):
            pose = PoseStamped()
            pose.header.stamp = rospy.Time.now()
            pose.pose.position.x = pos_traj[index][0]
            pose.pose.position.y = pos_traj[index][1]
            pose.pose.position.z = pos_traj[index][2]
        
        local_pos_pub.publish(pose)

        if(index < len(pos_traj) - 1):
            index += 1

        rate.sleep()


