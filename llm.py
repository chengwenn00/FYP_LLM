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
import matplotlib.pyplot as plt

from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest
from openai import OpenAI
from mpl_toolkits.mplot3d import Axes3D

current_state = State()



def plot_waypoints(start_point, end_point, waypoints):
    # Create a new figure
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # Unzip the start point and end point for plotting
    start_x, start_y, start_z = start_point
    end_x, end_y, end_z = end_point

    # Plot the starting point in green
    ax.scatter(start_x, start_y, start_z, color='green', s=100, label='Start Point')

    # Plot the ending point in red
    ax.scatter(end_x, end_y, end_z, color='red', s=100, label='End Point')

    # Unzip waypoints for plotting
    waypoints_x, waypoints_y, waypoints_z = zip(*waypoints)

    # Create a color map
    cmap = plt.get_cmap("viridis")  # You can choose other colormaps as well
    num_waypoints = len(waypoints)
    
    # Create a color array based on the number of waypoints
    colors = [cmap(i / (num_waypoints + 1)) for i in range(num_waypoints)]
    
    # Plot waypoints with a color scale
    ax.scatter(waypoints_x, waypoints_y, waypoints_z, color=colors, label='Waypoints')

    # Draw lines connecting the points
    # Combine all points for line plotting
    all_x = [start_x] + list(waypoints_x) + [end_x]
    all_y = [start_y] + list(waypoints_y) + [end_y]
    all_z = [start_z] + list(waypoints_z) + [end_z]

    # Plot lines connecting the points
    ax.plot(all_x, all_y, all_z, color='black', linewidth=2, label='Path')

    # Set labels
    ax.set_xlabel('X axis')
    ax.set_ylabel('Y axis')
    ax.set_zlabel('Z axis')

    # Set the title and legend
    ax.set_title('3D Waypoints Plot with Path')
    ax.legend()

    # Show the plot
    plt.show()



def state_cb(msg):
    global current_state
    # print(current_state)
    current_state = msg

# Initialize the LLaMA model client from NVIDIA NIM
client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = "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"
)

def add_intermediate_steps(waypoints, num_intermediate_points=100):
    new_waypoints = []

    # Iterate through each pair of adjacent waypoints
    for i in range(len(waypoints) - 1):
        start = waypoints[i]
        end = waypoints[i + 1]

        # Append the current waypoint to the new list
        new_waypoints.append(start)

        # Calculate the intermediate points
        for j in range(1, num_intermediate_points + 1):
            intermediate_point = [
                start[k] + (end[k] - start[k]) * (j / (num_intermediate_points + 1))
                for k in range(3)
            ]
            new_waypoints.append(intermediate_point)

    # Append the last waypoint to the new list
    new_waypoints.append(waypoints[-1])
    
    return new_waypoints

def get_drone_navigation_instructions(start, end, obstacles):
    # Prepare the prompt with the current navigation task
    prompt = (
        f"You are a drone navigating from point {start} to point {end}. "
        f"Your task is to plot the shortest route avoiding the following obstacles: {obstacles}. "
        f"Please provide the detailed navigation instructions in the (x, y, z) format."
    )

    # Create a chat completion request
    completion = client.chat.completions.create(
        model="meta/llama-3.1-8b-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        top_p=0.7,
        max_tokens=1024,
        stream=True
    )

    # Collect the instructions from the response
    instructions = ""
    for chunk in completion:
        if chunk.choices[0].delta.content is not None:
            instructions += chunk.choices[0].delta.content

    # Parse the response into waypoints
    waypoints = []
    for line in instructions.split("\n"):
        if "->" in line:  # Only process lines that have coordinates
            points = line.strip().split("->")
            for point in points:
                coords = point.strip("() ").split(",")
                if len(coords) == 3:
                    try:
                        # Ensure all elements are valid floats
                        waypoints.append([float(c) for c in coords])
                    except ValueError:
                        # Skip any invalid points
                        continue

    return waypoints

# # Function to get drone navigation instructions
# def get_drone_navigation_instructions(start, end, obstacles):
#     # Prepare the prompt with the current navigation task
#     prompt = (
#         f"You are a drone navigating from point {start} to point {end}. "
#         f"Your task is to plot the shortest route avoiding the following obstacles: {obstacles}. "
#         f"Please provide the detailed navigation instructions in the (x, y, z) format."
#     )

#     # Create a chat completion request
#     completion = client.chat.completions.create(
#         model="meta/llama-3.1-8b-instruct",
#         messages=[{"role": "user", "content": prompt}],
#         temperature=0.2,
#         top_p=0.7,
#         max_tokens=1024,
#         stream=True
#     )

#     # Collect the instructions from the response
#     instructions = ""
#     for chunk in completion:
#         if chunk.choices[0].delta.content is not None:
#             instructions += chunk.choices[0].delta.content

#     # Parse the response into waypoints
#     waypoints = []
#     for line in instructions.split("\n"):
#         if "->" in line:
#             points = line.strip().split("->")
#             for point in points:
#                 coords = point.strip("() ").split(",")
#                 if len(coords) == 3:
#                     waypoints.append([float(c) for c in coords])

#     return waypoints

if __name__ == "__main__":
    rospy.init_node("offb_node_py")

    state_sub = rospy.Subscriber("mavros/state", State, callback=state_cb)
    local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)

    rospy.wait_for_service("/mavros/cmd/arming")
    arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)

    rospy.wait_for_service("/mavros/set_mode")
    set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

    # Setpoint publishing MUST be faster than 2Hz
    rate = rospy.Rate(50)

    # Wait for Flight Controller connection
    while not rospy.is_shutdown() and not current_state.connected:
        rate.sleep()

    # Send a few setpoints before starting
    pose = PoseStamped()
    pose.header.stamp = rospy.Time.now()
    pose.pose.position.x = 0
    pose.pose.position.y = 3
    pose.pose.position.z = 1

    for i in range(100):
        if rospy.is_shutdown():
            break
        # print(pose)
        local_pos_pub.publish(pose)
        rate.sleep()

    # Define the start point, end point, and obstacles
    start_point = (0, 0, 0)
    end_point = (10, 10, 0)
    obstacle_list = [(2, 2, 0), (4, 5, 0), (6, 6, 0)]

    # Get the trajectory from the LLM
    pos_traj_ = get_drone_navigation_instructions(start_point, end_point, obstacle_list)
    pos_traj = add_intermediate_steps(pos_traj_, 99)
    print(pos_traj)

    # Plot the waypoints
    plot_waypoints(start_point, end_point, pos_traj)


    offb_set_mode = SetModeRequest()
    offb_set_mode.custom_mode = 'OFFBOARD'

    arm_cmd = CommandBoolRequest()
    arm_cmd.value = True

    last_req = rospy.Time.now()
    index = 0

    while not rospy.is_shutdown():
        if current_state.mode != "OFFBOARD" and (rospy.Time.now() - last_req) > rospy.Duration(5.0):
            if set_mode_client.call(offb_set_mode).mode_sent:
                rospy.loginfo("OFFBOARD enabled")
            last_req = rospy.Time.now()
        else:
            if not current_state.armed and (rospy.Time.now() - last_req) > rospy.Duration(5.0):
                if arming_client.call(arm_cmd).success:
                    rospy.loginfo("Vehicle armed")
                last_req = rospy.Time.now()

        # Publish the waypoints from the LLM-based trajectory
        if(pos_traj is not None):
            pose = PoseStamped()
            pose.header.stamp = rospy.Time.now()
            pose.pose.position.x = pos_traj[index][0]
            pose.pose.position.y = pos_traj[index][1]
            pose.pose.position.z = pos_traj[index][2]
            # print(pose)
            local_pos_pub.publish(pose)

        if index < len(pos_traj) - 1:
            index += 1

        rate.sleep()
