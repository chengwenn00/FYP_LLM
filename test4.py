# #!/usr/bin/env python

# import rospy
# import time
# import re
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# # Initialize the OpenAI API client
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# current_state = State()

# # Callback to update the current state
# def state_cb(msg):
#     global current_state
#     current_state = msg

# # ROS setup: Subscriber and publisher
# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)

# # Request navigation instructions from LLaMA
# def get_llm_navigation_instructions(start, end, obstacles):
#     prompt = (
#         f"Guide a drone from start {start} to end {end} while avoiding 2x2x2 obstacles at {obstacles}. "
#         "Provide a smooth, direct path with small steps (0.5 meters per step) to avoid obstacles and reach the destination efficiently. "
#         "Once the final waypoint is reached, stop and hold position at the endpoint."
#     )
    
#     try:
#         # Request LLaMA response
#         completion = client.chat.completions.create(
#             model="meta/llama-3.1-8b-instruct",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.2,
#             top_p=0.7,
#             max_tokens=1024,
#             stream=True
#         )
        
#         # Collect instructions
#         instructions = "".join(chunk.choices[0].delta.content for chunk in completion if chunk.choices[0].delta.content)
#         waypoints = parse_waypoints(instructions)
        
#         # Generate shortest path with finer intermediate waypoints, while avoiding obstacles
#         return generate_shortest_path_with_avoidance(waypoints, obstacles, threshold=0.5)
    
#     except Exception as e:
#         rospy.logerr(f"Error fetching navigation instructions: {e}")
#         return []  # Return empty waypoints list if API call fails

# # Parse waypoints from LLaMA response
# def parse_waypoints(instructions):
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, instructions):
#         waypoint = tuple(map(float, match.groups()))
#         waypoints.append(waypoint)
#     return waypoints

# # Generate shortest path with obstacle avoidance and finer intermediate waypoints
# def generate_shortest_path_with_avoidance(waypoints, obstacles, threshold=0.5):
#     refined_path = []
#     last_point = waypoints[0]

#     for waypoint in waypoints:
#         # Check if the waypoint is too close to any obstacle
#         too_close = False
#         for obs in obstacles:
#             if (abs(waypoint[0] - obs[0]) < 1.5 and abs(waypoint[1] - obs[1]) < 1.5 and abs(waypoint[2] - obs[2]) < 1.5):
#                 too_close = True
#                 detour_waypoints = create_detour_around_obstacle(last_point, waypoint, obs)
#                 refined_path.extend(detour_waypoints)
#                 last_point = detour_waypoints[-1]
#                 break

#         if not too_close:
#             # Add intermediate points if distance exceeds threshold
#             distance = sum((waypoint[i] - last_point[i]) ** 2 for i in range(3)) ** 0.5
#             if distance > threshold:
#                 num_intermediate_steps = int(distance // threshold)
#                 for step in range(1, num_intermediate_steps + 1):
#                     intermediate_waypoint = tuple(
#                         last_point[i] + (waypoint[i] - last_point[i]) * step / (num_intermediate_steps + 1) for i in range(3)
#                     )
#                     refined_path.append(intermediate_waypoint)

#             refined_path.append(waypoint)
#             last_point = waypoint

#     return refined_path

# # Function to create detour around a given obstacle
# def create_detour_around_obstacle(start, end, obstacle, detour_distance=2.0):
#     detour_path = []
#     ox, oy, oz = obstacle
#     sx, sy, sz = start
#     ex, ey, ez = end

#     if abs(ex - ox) > abs(ey - oy):  # Detour along y-axis
#         if sy < oy:
#             detour_path.append((sx, oy - detour_distance, sz))
#         else:
#             detour_path.append((sx, oy + detour_distance, sz))
#         detour_path.append((ex, detour_path[-1][1], ez))
#     else:  # Detour along x-axis
#         if sx < ox:
#             detour_path.append((ox - detour_distance, sy, sz))
#         else:
#             detour_path.append((ox + detour_distance, sy, sz))
#         detour_path.append((detour_path[-1][0], ey, ez))

#     return detour_path

# # Execute the trajectory, stopping and staying at the final waypoint
# def execute_trajectory(path_instructions):
#     pose = PoseStamped()
#     rate = rospy.Rate(20)

#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     offb_set_mode = SetModeRequest()
#     offb_set_mode.custom_mode = 'OFFBOARD'
#     arm_cmd = CommandBoolRequest()
#     arm_cmd.value = True

#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()
    
#     rospy.loginfo(f"Mode: {current_state.mode}, Armed: {current_state.armed}, Connected: {current_state.connected}")

#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     if current_state.mode != "OFFBOARD":
#         set_mode_client.call(offb_set_mode)
#         rospy.loginfo("OFFBOARD mode set")
#     if not current_state.armed:
#         arming_client.call(arm_cmd)
#         rospy.loginfo("Drone armed")

#     for idx, waypoint in enumerate(path_instructions):
#         x, y, z = waypoint
#         pose.pose.position.x = x
#         pose.pose.position.y = y
#         pose.pose.position.z = z
#         rospy.loginfo(f"Publishing waypoint: {waypoint}")
        
#         for _ in range(10):
#             local_pos_pub.publish(pose)
#             rate.sleep()
        
#         if idx == len(path_instructions) - 1:
#             rospy.loginfo("Final waypoint reached, holding position at the final waypoint.")
#             while not rospy.is_shutdown():
#                 local_pos_pub.publish(pose)
#                 rate.sleep()
#             break

# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     start_point = (0.0, 3.0, 1.0)
#     end_point = (0.0, 3.0, 9.0)
    
#     obstacle_list = [
#         (0.0, 3.0, 5.0)
#     ]

#     refined_path = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
    
#     if refined_path:
#         execute_trajectory(refined_path)
#     else:
#         rospy.logerr("No path found to the destination.")

#!/usr/bin/env python

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

current_state = State()

# Callback to update the current state
def state_cb(msg):
    global current_state
    current_state = msg

# ROS setup: Subscriber and publisher
local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
rospy.Subscriber("mavros/state", State, state_cb)

# Request navigation instructions from LLaMA with obstacle detour
def get_llm_navigation_instructions(start, end, obstacles):
    obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
    prompt = (
        f"Guide a drone from start {start} to end {end} while avoiding all obstacles of 2x2x2 units at locations: {obstacle_str}. "
        "Plan a path that entirely detours around these obstacles, providing smooth and efficient waypoints. "
        "Use 0.5-meter steps for precision and smooth transitions around obstacles, stopping at the endpoint."
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
        waypoints = parse_waypoints(instructions)
        
        return waypoints
    
    except Exception as e:
        rospy.logerr(f"Error fetching navigation instructions: {e}")
        return []  # Return empty waypoints list if API call fails

# Parse waypoints from LLaMA response
def parse_waypoints(instructions):
    waypoints = []
    pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
    for match in re.finditer(pattern, instructions):
        waypoint = tuple(map(float, match.groups()))
        waypoints.append(waypoint)
    return waypoints

# Generate smooth path with intermediate waypoints and obstacle avoidance
def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.05):
    refined_path = []
    last_point = waypoints[0]

    for waypoint in waypoints:
        # Calculate distance between the last point and current waypoint
        distance = sum((waypoint[i] - last_point[i]) ** 2 for i in range(3)) ** 0.5

        # Generate intermediate waypoints for smooth transition
        num_intermediate_steps = int(distance // step_size)
        for step in range(1, num_intermediate_steps + 1):
            intermediate_waypoint = tuple(
                last_point[i] + (waypoint[i] - last_point[i]) * step / (num_intermediate_steps + 1) for i in range(3)
            )
            refined_path.append(intermediate_waypoint)
        
        refined_path.append(waypoint)
        last_point = waypoint

    # Ensure obstacle avoidance in path planning
    refined_path = avoid_obstacles(refined_path, obstacles, step_size)
    return refined_path

# Obstacle avoidance by adjusting path to bypass obstacles entirely
def avoid_obstacles(path, obstacles, step_size):
    obstacle_clearance = 1.1  # Clearance around obstacle in meters
    safe_path = []
    for idx, point in enumerate(path):
        safe = True
        for obstacle in obstacles:
            obs_x, obs_y, obs_z = obstacle
            # Define bounding box for the obstacle
            if (obs_x - 1 <= point[0] <= obs_x + 1 and
                obs_y - 1 <= point[1] <= obs_y + 1 and
                obs_z - 1 <= point[2] <= obs_z + 1):
                # Obstacle detected within the path
                safe = False
                break

        if safe:
            safe_path.append(point)
        else:
            # Generate detour waypoints if too close to an obstacle
            detour_waypoints = create_detour_around_obstacle(path[idx - 1], point, obstacle, obstacle_clearance)
            safe_path.extend(detour_waypoints)

    return safe_path

# Detour creation with step size for obstacle avoidance
def create_detour_around_obstacle(start, end, obstacle, clearance_distance=1.1):
    detour_path = []
    ox, oy, oz = obstacle
    sx, sy, sz = start
    ex, ey, ez = end

    if abs(ex - ox) > abs(ey - oy):  # Detour along y-axis
        if sy < oy:
            detour_path.append((sx, oy - clearance_distance, sz))
        else:
            detour_path.append((sx, oy + clearance_distance, sz))
        detour_path.append((ex, detour_path[-1][1], ez))
    else:  # Detour along x-axis
        if sx < ox:
            detour_path.append((ox - clearance_distance, sy, sz))
        else:
            detour_path.append((ox + clearance_distance, sy, sz))
        detour_path.append((detour_path[-1][0], ey, ez))

    # Add more waypoints for smoothness in detour
    smoothed_detour_path = generate_smooth_path_with_intermediate_waypoints(detour_path, [], step_size=0.05)
    return smoothed_detour_path

# Execute the trajectory, stopping and staying at the final waypoint
def execute_trajectory(path_instructions):
    pose = PoseStamped()
    rate = rospy.Rate(20)

    rospy.wait_for_service("/mavros/cmd/arming")
    arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
    rospy.wait_for_service("/mavros/set_mode")
    set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

    offb_set_mode = SetModeRequest()
    offb_set_mode.custom_mode = 'OFFBOARD'
    arm_cmd = CommandBoolRequest()
    arm_cmd.value = True

    # Wait for connection
    while not rospy.is_shutdown() and not current_state.connected:
        rate.sleep()
    
    rospy.loginfo(f"Mode: {current_state.mode}, Armed: {current_state.armed}, Connected: {current_state.connected}")

    # Publish a few initial setpoints before starting
    for _ in range(200):
        local_pos_pub.publish(pose)
        rate.sleep()

    # Set mode to OFFBOARD and arm the drone if not already done
    if current_state.mode != "OFFBOARD":
        set_mode_client.call(offb_set_mode)
        rospy.loginfo("OFFBOARD mode set")
    if not current_state.armed:
        arming_client.call(arm_cmd)
        rospy.loginfo("Drone armed")

    # Define the buffer for the final position
    final_x, final_y, final_z = path_instructions[-1]
    position_buffer = 0.1  # 0.1 meters tolerance in each direction

    # Go through the waypoints until reaching the final waypoint
    for idx, waypoint in enumerate(path_instructions):
        x, y, z = waypoint
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = z
        rospy.loginfo(f"Publishing waypoint: {waypoint}")
        
        # Publish the waypoint multiple times to ensure the drone reaches it
        for _ in range(10):
            local_pos_pub.publish(pose)
            rate.sleep()
        
        # If the final waypoint is reached, break the loop and hold the position
        if idx == len(path_instructions) - 1:
            rospy.loginfo("Final waypoint reached. Holding position at the final waypoint.")
            break

    # Hold position at the final waypoint indefinitely
    while not rospy.is_shutdown():
        pose.pose.position.x = final_x
        pose.pose.position.y = final_y
        pose.pose.position.z = final_z
        local_pos_pub.publish(pose)
        rate.sleep()


# Main function initialization and execution
if __name__ == "__main__":
    rospy.init_node("drone_navigation_node")
    start_point = (0.0, 3.0, 1.0)
    end_point = (0.0, -7.0, 1.0)
    
    obstacle_list = [
        (0.0, 0.0, 1.0), (0.0, -4.0, 1.0)
    ]

    refined_path = generate_smooth_path_with_intermediate_waypoints(get_llm_navigation_instructions(start_point, end_point, obstacle_list), obstacle_list)
    
    if refined_path:
        execute_trajectory(refined_path)
    else:
        rospy.logerr("No path found to the destination.")



