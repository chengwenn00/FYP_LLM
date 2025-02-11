#!/usr/bin/env python

"""
 * File: offb_node.py
 * Stack and tested in Gazebo Classic 9 SITL
"""

import rospy
import time
import re
from openai import OpenAI
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# Initialize the OpenAI API client
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

# Initialize current state of the drone
current_state = State()

# Callback to update the current state
def state_cb(msg):
    global current_state
    current_state = msg

# ROS setup: Subscriber and publisher
local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
rospy.Subscriber("mavros/state", State, state_cb)

# Function to request navigation instructions from LLaMA
def get_drone_navigation_instructions(start, end, obstacles):
    prompt = (
        f"You are navigating a drone from start {start} to end {end} while avoiding obstacles: {obstacles}. "
        "Generate waypoints in (x, y, z) format to safely reach the destination."
    )
    
    try:
        # Request LLaMA response
        completion = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            top_p=0.7,
            max_tokens=1024,
            stream=True
        )
        
        # Collect instructions
        instructions = "".join(chunk.choices[0].delta.content for chunk in completion if chunk.choices[0].delta.content)
        return parse_waypoints(instructions)
    
    except Exception as e:
        rospy.logerr(f"Error fetching navigation instructions: {e}")
        return []  # Return empty waypoints list if API call fails

# Function to parse waypoints from LLaMA response
def parse_waypoints(instructions):
    waypoints = []
    pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
    for match in re.finditer(pattern, instructions):
        waypoint = tuple(map(float, match.groups()))
        waypoints.append(waypoint)
    return waypoints

# Function to add intermediate steps for smooth waypoint transitions
def add_intermediate_steps(waypoints, threshold=0.5):
    smooth_path = []
    for i in range(len(waypoints) - 1):
        start, end = waypoints[i], waypoints[i + 1]
        smooth_path.append(start)
        dist = sum((end[j] - start[j])**2 for j in range(3))**0.5
        if dist > threshold:
            steps = int(dist / threshold)
            for j in range(1, steps):
                interp_point = tuple(start[k] + (end[k] - start[k]) * j / steps for k in range(3))
                smooth_path.append(interp_point)
    smooth_path.append(waypoints[-1])
    return smooth_path

# Execute the trajectory using the waypoints
def execute_trajectory(path_instructions):
    pose = PoseStamped()
    rate = rospy.Rate(20)

    # Initialize offboard mode and arm the drone
    rospy.wait_for_service("/mavros/cmd/arming")
    arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
    rospy.wait_for_service("/mavros/set_mode")
    set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

    # Setup offboard mode and arming requests
    offb_set_mode = SetModeRequest()
    offb_set_mode.custom_mode = 'OFFBOARD'
    arm_cmd = CommandBoolRequest()
    arm_cmd.value = True

    # Wait until the drone is connected
    while not rospy.is_shutdown() and not current_state.connected:
        rate.sleep()
    
    # Log the state before entering offboard mode and arming
    rospy.loginfo(f"Mode: {current_state.mode}, Armed: {current_state.armed}, Connected: {current_state.connected}")

    # Send initial setpoints to stabilize before starting
    for _ in range(200):  # Increased from 100 to 200 cycles
        local_pos_pub.publish(pose)
        rate.sleep()

    # Set OFFBOARD mode and arm the drone
    if current_state.mode != "OFFBOARD":
        set_mode_client.call(offb_set_mode)
        rospy.loginfo("OFFBOARD mode set")
    if not current_state.armed:
        arming_client.call(arm_cmd)
        rospy.loginfo("Drone armed")

    # Publish each waypoint for a few cycles to ensure stable movement
    for waypoint in path_instructions:
        x, y, z = waypoint
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = z
        rospy.loginfo(f"Publishing waypoint: {waypoint}")  # Log each waypoint
        for _ in range(10):  # Publish each waypoint multiple times
            local_pos_pub.publish(pose)
            rate.sleep()

if __name__ == "__main__":
    rospy.init_node("drone_navigation_node")
    start_point = (0.0, 3.0, 1.0)
    end_point = (0.0, 3.0, 3.0)
    obstacle_list = []
    
    # Get the navigation path from the LLaMA model
    raw_instructions = get_drone_navigation_instructions(start_point, end_point, obstacle_list)
    refined_path = add_intermediate_steps(raw_instructions, threshold=0.5)
    
    # Execute the trajectory
    execute_trajectory(refined_path)

