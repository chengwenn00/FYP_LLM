# # #!/usr/bin/env python

# # import rospy
# # import time
# # import re
# # from openai import OpenAI
# # from geometry_msgs.msg import PoseStamped
# # from mavros_msgs.msg import State
# # from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# # # Initialize the OpenAI API client
# # client = OpenAI(
# #     base_url="https://integrate.api.nvidia.com/v1",
# #     api_key="YOUR_API_KEY"
# # )

# # current_state = State()

# # # Callback to update the current state
# # def state_cb(msg):
# #     global current_state
# #     current_state = msg

# # # ROS setup: Subscriber and publisher
# # local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# # rospy.Subscriber("mavros/state", State, state_cb)

# # # Request navigation instructions from LLaMA
# # def get_drone_navigation_instructions(start, end, obstacles):
# #     prompt = (
# #         f"You are navigating a drone from start {start} to end {end} while avoiding obstacles: {obstacles}. "
# #         "Generate waypoints in (x, y, z) format for the shortest and most accurate path."
# #     )
    
# #     try:
# #         # Request LLaMA response
# #         completion = client.chat.completions.create(
# #             model="meta/llama-3.1-8b-instruct",
# #             messages=[{"role": "user", "content": prompt}],
# #             temperature=0.2,
# #             top_p=0.7,
# #             max_tokens=1024,
# #             stream=True
# #         )
        
# #         # Collect instructions
# #         instructions = "".join(chunk.choices[0].delta.content for chunk in completion if chunk.choices[0].delta.content)
# #         return parse_waypoints(instructions)
    
# #     except Exception as e:
# #         rospy.logerr(f"Error fetching navigation instructions: {e}")
# #         return []  # Return empty waypoints list if API call fails

# # # Parse waypoints from LLaMA response
# # def parse_waypoints(instructions):
# #     waypoints = []
# #     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
# #     for match in re.finditer(pattern, instructions):
# #         waypoint = tuple(map(float, match.groups()))
# #         waypoints.append(waypoint)
# #     return waypoints

# # # Add intermediate steps for a straight path
# # def add_intermediate_steps(start, end, threshold=0.5):
# #     smooth_path = [start]
# #     distance = sum((end[i] - start[i])**2 for i in range(3))**0.5
# #     steps = int(distance / threshold)
    
# #     # Generate waypoints from start to end directly
# #     for step in range(1, steps + 1):
# #         waypoint = tuple(start[i] + (end[i] - start[i]) * step / steps for i in range(3))
# #         smooth_path.append(waypoint)
    
# #     return smooth_path

# # # Execute the trajectory, stopping at the final waypoint
# # def execute_trajectory(path_instructions):
# #     pose = PoseStamped()
# #     rate = rospy.Rate(20)

# #     # Initialize offboard mode and arm the drone
# #     rospy.wait_for_service("/mavros/cmd/arming")
# #     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
# #     rospy.wait_for_service("/mavros/set_mode")
# #     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

# #     # Setup offboard mode and arming requests
# #     offb_set_mode = SetModeRequest()
# #     offb_set_mode.custom_mode = 'OFFBOARD'
# #     arm_cmd = CommandBoolRequest()
# #     arm_cmd.value = True

# #     # Wait until the drone is connected
# #     while not rospy.is_shutdown() and not current_state.connected:
# #         rate.sleep()
    
# #     # Log the state before entering offboard mode and arming
# #     rospy.loginfo(f"Mode: {current_state.mode}, Armed: {current_state.armed}, Connected: {current_state.connected}")

# #     # Send initial setpoints to stabilize before starting
# #     for _ in range(200):
# #         local_pos_pub.publish(pose)
# #         rate.sleep()

# #     # Set OFFBOARD mode and arm the drone
# #     if current_state.mode != "OFFBOARD":
# #         set_mode_client.call(offb_set_mode)
# #         rospy.loginfo("OFFBOARD mode set")
# #     if not current_state.armed:
# #         arming_client.call(arm_cmd)
# #         rospy.loginfo("Drone armed")

# #     # Publish each waypoint and stop once final waypoint is reached
# #     for idx, waypoint in enumerate(path_instructions):
# #         x, y, z = waypoint
# #         pose.pose.position.x = x
# #         pose.pose.position.y = y
# #         pose.pose.position.z = z
# #         rospy.loginfo(f"Publishing waypoint: {waypoint}")  # Log each waypoint
        
# #         for _ in range(10):  # Publish each waypoint multiple times for stability
# #             local_pos_pub.publish(pose)
# #             rate.sleep()
        
# #         # Stop if the final waypoint is reached
# #         if idx == len(path_instructions) - 1:
# #             rospy.loginfo("Final waypoint reached, stopping the drone.")
# #             break

# # if __name__ == "__main__":
# #     rospy.init_node("drone_navigation_node")
# #     start_point = (0.0, 3.0, 1.0)
# #     end_point = (0.0, 3.0, 3.0)
# #     obstacle_list = []
    
# #     # Generate a direct path with intermediate waypoints
# #     refined_path = add_intermediate_steps(start_point, end_point, threshold=0.5)
    
# #     # Execute the trajectory
# #     execute_trajectory(refined_path)
# #!/usr/bin/env python

# import rospy
# import time
# import re
# import heapq
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# # Initialize the OpenAI API client
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="YOUR_API_KEY"
# )

# current_state = State()

# # Callback to update the current state
# def state_cb(msg):
#     global current_state
#     current_state = msg

# # ROS setup: Subscriber and publisher
# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)

# # Define A* pathfinding for obstacle avoidance
# def a_star_pathfinding(start, end, obstacles, threshold=0.5):
#     open_set = []
#     heapq.heappush(open_set, (0, start))
#     came_from = {}
#     g_score = {start: 0}
#     f_score = {start: heuristic(start, end)}

#     while open_set:
#         _, current = heapq.heappop(open_set)

#         if current == end:
#             return reconstruct_path(came_from, current)

#         for neighbor in get_neighbors(current, threshold):
#             if neighbor in obstacles:
#                 continue
#             tentative_g_score = g_score[current] + distance(current, neighbor)

#             if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
#                 came_from[neighbor] = current
#                 g_score[neighbor] = tentative_g_score
#                 f_score[neighbor] = tentative_g_score + heuristic(neighbor, end)
#                 heapq.heappush(open_set, (f_score[neighbor], neighbor))

#     return []  # Return empty path if no route found

# # Heuristic function for A* (Euclidean distance)
# def heuristic(point1, point2):
#     return sum((a - b) ** 2 for a, b in zip(point1, point2)) ** 0.5

# # Distance between two points
# def distance(point1, point2):
#     return heuristic(point1, point2)

# # Get neighbors for pathfinding (8 directions in 3D space)
# def get_neighbors(point, step_size):
#     x, y, z = point
#     directions = [
#         (x + step_size, y, z), (x - step_size, y, z),
#         (x, y + step_size, z), (x, y - step_size, z),
#         (x, y, z + step_size), (x, y, z - step_size)
#     ]
#     return directions

# # Reconstruct path from A* algorithm
# def reconstruct_path(came_from, current):
#     path = [current]
#     while current in came_from:
#         current = came_from[current]
#         path.append(current)
#     path.reverse()
#     return path

# # Execute the trajectory, stopping at the final waypoint
# def execute_trajectory(path_instructions):
#     pose = PoseStamped()
#     rate = rospy.Rate(20)

#     # Initialize offboard mode and arm the drone
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     # Setup offboard mode and arming requests
#     offb_set_mode = SetModeRequest()
#     offb_set_mode.custom_mode = 'OFFBOARD'
#     arm_cmd = CommandBoolRequest()
#     arm_cmd.value = True

#     # Wait until the drone is connected
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()
    
#     # Log the state before entering offboard mode and arming
#     rospy.loginfo(f"Mode: {current_state.mode}, Armed: {current_state.armed}, Connected: {current_state.connected}")

#     # Send initial setpoints to stabilize before starting
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     # Set OFFBOARD mode and arm the drone
#     if current_state.mode != "OFFBOARD":
#         set_mode_client.call(offb_set_mode)
#         rospy.loginfo("OFFBOARD mode set")
#     if not current_state.armed:
#         arming_client.call(arm_cmd)
#         rospy.loginfo("Drone armed")

#     # Publish each waypoint and stop once final waypoint is reached
#     for idx, waypoint in enumerate(path_instructions):
#         x, y, z = waypoint
#         pose.pose.position.x = x
#         pose.pose.position.y = y
#         pose.pose.position.z = z
#         rospy.loginfo(f"Publishing waypoint: {waypoint}")  # Log each waypoint
        
#         for _ in range(10):  # Publish each waypoint multiple times for stability
#             local_pos_pub.publish(pose)
#             rate.sleep()
        
#         # Stop if the final waypoint is reached
#         if idx == len(path_instructions) - 1:
#             rospy.loginfo("Final waypoint reached, stopping the drone.")
#             break

# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     start_point = (0.0, 3.0, 1.0)
#     end_point = (0.0, 3.0, 8.0)
    
#     # Define some obstacles in the path
#     obstacle_list = [
#         (0.0, 3.0, 1.5),  # Obstacle near the starting point
#         (0.0, 3.0, 2.5),  # Obstacle in between  # Obstacle off to the side
#     ]

#     # Generate a path that avoids obstacles
#     refined_path = a_star_pathfinding(start_point, end_point, obstacle_list, threshold=0.5)
    
#     # Execute the trajectory if a path is found
#     if refined_path:
#         execute_trajectory(refined_path)
#     else:
#         rospy.logerr("No path found to the destination.")


#!/usr/bin/env python

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

# Request navigation instructions from LLaMA
def get_llm_navigation_instructions(start, end, obstacles):
    prompt = (
        f"Guide a drone from start {start} to end {end} while avoiding 2x2 obstacles at {obstacles}. "
        "Provide a smooth, continuous path with small steps (0.5 meters per step) to avoid obstacles and reach the destination. "
        "Once the final waypoint is reached, stop and hold position at the endpoint."
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
        
        # Verify waypoints for continuity and obstacle avoidance with finer intermediate steps
        return generate_precise_waypoints(waypoints, obstacles, threshold=0.5)
    
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

# Generate precise waypoints with more intermediate steps and obstacle avoidance
def generate_precise_waypoints(waypoints, obstacles, threshold=0.5):
    refined_path = []
    last_point = waypoints[0]

    for waypoint in waypoints:
        # Skip waypoints too close to obstacles
        if any(sum((waypoint[i] - obs[i]) ** 2 for i in range(3)) ** 0.5 < 1.0 for obs in obstacles):
            rospy.logwarn(f"Waypoint {waypoint} is too close to an obstacle and will be skipped.")
            continue

        # Calculate distance between consecutive waypoints for continuity
        distance = sum((waypoint[i] - last_point[i]) ** 2 for i in range(3)) ** 0.5
        
        # If the distance is greater than the threshold, add finer intermediate points
        if distance > threshold:
            num_intermediate_steps = int(distance // threshold)
            for step in range(1, num_intermediate_steps + 1):
                intermediate_waypoint = tuple(
                    last_point[i] + (waypoint[i] - last_point[i]) * step / (num_intermediate_steps + 1) for i in range(3)
                )
                refined_path.append(intermediate_waypoint)
        
        refined_path.append(waypoint)
        last_point = waypoint
    
    return refined_path

# Execute the trajectory, stopping and staying at the final waypoint
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
    for _ in range(200):
        local_pos_pub.publish(pose)
        rate.sleep()

    # Set OFFBOARD mode and arm the drone
    if current_state.mode != "OFFBOARD":
        set_mode_client.call(offb_set_mode)
        rospy.loginfo("OFFBOARD mode set")
    if not current_state.armed:
        arming_client.call(arm_cmd)
        rospy.loginfo("Drone armed")

    # Publish each waypoint and stop once the final waypoint is reached
    for idx, waypoint in enumerate(path_instructions):
        x, y, z = waypoint
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = z
        rospy.loginfo(f"Publishing waypoint: {waypoint}")  # Log each waypoint
        
        for _ in range(10):  # Publish each waypoint multiple times for stability
            local_pos_pub.publish(pose)
            rate.sleep()
        
        # Stop at the final waypoint
        if idx == len(path_instructions) - 1:
            rospy.loginfo("Final waypoint reached, holding position at the final waypoint.")
            while not rospy.is_shutdown():
                local_pos_pub.publish(pose)  # Keep publishing the final position to maintain position
                rate.sleep()
            break

if __name__ == "__main__":
    rospy.init_node("drone_navigation_node")
    start_point = (0.0, 3.0, 1.0)
    end_point = (0.0, 3.0, 8.0)
    
    # Define some obstacles in the path
    obstacle_list = [
        (0.0, 3.0, 1.5),  # Obstacle near the starting point
        (0.0, 3.0, 2.5),  # Obstacle in between
    ]

    # Use LLM to generate a path that avoids obstacles
    refined_path = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
    
    # Execute the trajectory if a path is found
    if refined_path:
        execute_trajectory(refined_path)
    else:
        rospy.logerr("No path found to the destination.")
