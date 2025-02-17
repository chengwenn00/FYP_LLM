# import rospy
# import time
# import re
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# # Initialize the OpenAI API client with NVIDIA NIM endpoint
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

# # Request navigation instructions from DeepSeek R1 with obstacle detour
# def get_llm_navigation_instructions(start, end, obstacles):
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         f"Guide a drone from start {start} to end {end} while avoiding all obstacles of 2x2x2 units at locations: {obstacle_str}. "
#         "Plan a path that detours smoothly around these obstacles, with each waypoint moving closer to the endpoint, avoiding backtracking, and following a smooth trajectory."
#     )
    
#     rospy.loginfo("Sending prompt to DeepSeek model: %s", prompt)
#     try:
#         # Request DeepSeek R1 response instead of LLaMA
#         completion = client.chat.completions.create(
#             model="deepseek-ai/deepseek-r1",  # Updated model name for DeepSeek R1
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.6,
#             top_p=0.7,
#             max_tokens=1024,
#             stream=False  # Using non-streaming mode
#         )
        
#         rospy.loginfo("Received response from DeepSeek model.")
#         # Extract instructions from the response (assuming non-streaming mode)
#         instructions = completion.choices[0].message['content']
#         rospy.loginfo("Instructions received: %s", instructions)
#         waypoints = parse_waypoints(instructions)
#         rospy.loginfo("Parsed waypoints: %s", waypoints)
        
#         return waypoints
    
#     except Exception as e:
#         rospy.logerr("Error fetching navigation instructions: %s", e)
#         return []  # Return empty waypoints list if API call fails

# # Parse waypoints from LLM response
# def parse_waypoints(instructions):
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, instructions):
#         waypoint = tuple(map(float, match.groups()))
#         waypoints.append(waypoint)
#     return waypoints

# # Check if the new point is closer to the endpoint than the previous point to prevent backtracking
# def is_closer_to_endpoint(new_point, last_point, endpoint):
#     new_dist = sum((new_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
#     last_dist = sum((last_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
#     return new_dist < last_dist

# # Generate a smooth path that strictly progresses towards the endpoint, avoiding obstacles
# def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
#     refined_path = []
#     last_point = waypoints[0]

#     for waypoint in waypoints:
#         distance = sum((waypoint[i] - last_point[i]) ** 2 for i in range(3)) ** 0.5
#         direction = [(waypoint[i] - last_point[i]) / distance for i in range(3)] if distance > 0 else [0, 0, 0]

#         num_intermediate_steps = int(distance // step_size)
#         for step in range(1, num_intermediate_steps + 1):
#             intermediate_waypoint = tuple(
#                 last_point[i] + direction[i] * step * step_size for i in range(3)
#             )
#             if is_closer_to_endpoint(intermediate_waypoint, last_point, waypoints[-1]):
#                 refined_path.append(intermediate_waypoint)
        
#         if is_closer_to_endpoint(waypoint, last_point, waypoints[-1]):
#             refined_path.append(waypoint)
        
#         last_point = waypoint

#     refined_path = avoid_obstacles(refined_path, obstacles, step_size)
#     return refined_path

# # Refined obstacle avoidance to ensure forward-only progression
# def avoid_obstacles(path, obstacles, step_size):
#     safe_path = []
#     obstacle_clearance = 1.1
#     for idx, point in enumerate(path):
#         safe = True
#         for obs_x, obs_y, obs_z in obstacles:
#             if (obs_x - 1 <= point[0] <= obs_x + 1 and
#                 obs_y - 1 <= point[1] <= obs_y + 1 and
#                 obs_z - 1 <= point[2] <= obs_z + 1):
#                 safe = False
#                 break

#         if safe:
#             safe_path.append(point)
#         else:
#             rospy.loginfo("Point %s is too close to an obstacle. Creating detour...", point)
#             detour_waypoints = create_detour(point, path[idx + 1] if idx + 1 < len(path) else path[-1], obstacles)
#             rospy.loginfo("Detour waypoints created: %s", detour_waypoints)
#             safe_path.extend(detour_waypoints)

#     return safe_path

# # Refined detour to prevent backtracking
# def create_detour(start, end, obstacles, clearance=1.1):
#     detour_path = []
#     for obs in obstacles:
#         sx, sy, sz = start
#         ex, ey, ez = end
#         ox, oy, oz = obs
        
#         if abs(ex - ox) > abs(ey - oy):
#             if sy < oy:
#                 detour_path.append((sx, oy - clearance, sz))
#             else:
#                 detour_path.append((sx, oy + clearance, sz))
#             detour_path.append((ex, detour_path[-1][1], ez))
#         else:
#             if sx < ox:
#                 detour_path.append((ox - clearance, sy, sz))
#             else:
#                 detour_path.append((ox + clearance, sy, sz))
#             detour_path.append((detour_path[-1][0], ey, ez))

#     return detour_path

# # Execute the trajectory and hold the final waypoint
# def execute_trajectory(path_instructions, end_point):
#     pose = PoseStamped()
#     rate = rospy.Rate(20)

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     offb_set_mode = SetModeRequest()
#     offb_set_mode.custom_mode = 'OFFBOARD'
#     arm_cmd = CommandBoolRequest()
#     arm_cmd.value = True

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     # Publish some setpoints before starting offboard mode
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         set_mode_client.call(offb_set_mode)
#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         arming_client.call(arm_cmd)

#     # Execute and log each waypoint
#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         x, y, z = waypoint
#         pose.pose.position.x = x
#         pose.pose.position.y = y
#         pose.pose.position.z = z

#         rospy.loginfo("Navigating to waypoint %d: (%.3f, %.3f, %.3f)", idx, x, y, z)
#         for _ in range(10):
#             local_pos_pub.publish(pose)
#             rate.sleep()

#         if waypoint == end_point:
#             break

#     rospy.loginfo("Final waypoint reached. Holding position.")
#     # Hold the final position
#     while not rospy.is_shutdown():
#         pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
#         local_pos_pub.publish(pose)
#         rate.sleep()

# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     rospy.loginfo("Drone navigation node started.")
#     start_point = (0.0, 1, 0.5)
#     end_point = (0.0, -6.5, 0.5)
    
#     obstacle_list = [
#         (0.0, -1.5, 0.5),
#         (0.01, -5.51, 0.5)
#     ]
    
#     rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
#     waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     if waypoints:
#         rospy.loginfo("Waypoints received: %s", waypoints)
#         # Ensure the final waypoint matches the endpoint
#         waypoints[-1] = end_point
#         refined_path = generate_smooth_path_with_intermediate_waypoints(waypoints, obstacle_list)
        
#         rospy.loginfo("Final refined path with intermediate waypoints: %s", refined_path)
        
#         execute_trajectory(refined_path, end_point)
#     else:
#         rospy.logerr("No path found to the destination.")
#!/usr/bin/env python3
#!/usr/bin/env python3


# # !/usr/bin/env python3
# import rospy
# import time
# import re
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# # Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek)
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# current_state = State()

# # Callback to update the current state
# def state_cb(msg):
#     global current_state
#     current_state = msg

# # ROS setup: Subscriber and Publisher
# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)

# # Request navigation instructions from DeepSeek R1 with obstacle detour
# def get_llm_navigation_instructions(start, end, obstacles):
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         f"Guide a drone from start {start} to end {end} while avoiding obstacles at: {obstacle_str}. "
#         "Plan a smooth path with waypoints that steadily progress towards the endpoint without backtracking. "
#         "Return ONLY the path as a list of waypoints in the format (x, y, z), with each waypoint on a new line."
#     )
    
#     rospy.loginfo("Sending prompt to DeepSeek model: %s", prompt)
#     try:
#         completion = client.chat.completions.create(
#             model="deepseek-ai/deepseek-r1",  # DeepSeek model endpoint
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.6,
#             top_p=0.7,
#             max_tokens=1024,
#             stream=False  # Using non-streaming mode
#         )
        
#         rospy.loginfo("Raw response from DeepSeek: %s", completion)
        
#         # Check if the response is a raw string or a structured object
#         if isinstance(completion, str):
#             instructions = completion
#         elif hasattr(completion, "choices") and completion.choices:
#             if hasattr(completion.choices[0], "message"):
#                 instructions = completion.choices[0].message.content
#             elif hasattr(completion.choices[0], "text"):
#                 instructions = completion.choices[0].text
#             else:
#                 instructions = ""
#         else:
#             instructions = ""
            
#         rospy.loginfo("Extracted instructions: %s", instructions)
#         waypoints = parse_waypoints(instructions)
#         rospy.loginfo("Parsed waypoints: %s", waypoints)
        
#         return waypoints
    
#     except Exception as e:
#         rospy.logerr("Error fetching navigation instructions: %s", e)
#         return []  # Return empty list if API call fails

# # Parse waypoints from LLM response (expects format: (x, y, z))
# def parse_waypoints(instructions):
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, instructions):
#         waypoint = tuple(map(float, match.groups()))
#         waypoints.append(waypoint)
#     return waypoints

# # Check if the new point is closer to the endpoint than the previous point to prevent backtracking
# def is_closer_to_endpoint(new_point, last_point, endpoint):
#     new_dist = sum((new_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
#     last_dist = sum((last_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
#     return new_dist < last_dist

# # Generate a smooth path that strictly progresses towards the endpoint, avoiding obstacles
# def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
#     refined_path = []
#     last_point = waypoints[0]

#     for waypoint in waypoints:
#         distance = sum((waypoint[i] - last_point[i]) ** 2 for i in range(3)) ** 0.5
#         direction = [(waypoint[i] - last_point[i]) / distance for i in range(3)] if distance > 0 else [0, 0, 0]

#         num_intermediate_steps = int(distance // step_size)
#         for step in range(1, num_intermediate_steps + 1):
#             intermediate_waypoint = tuple(
#                 last_point[i] + direction[i] * step * step_size for i in range(3)
#             )
#             if is_closer_to_endpoint(intermediate_waypoint, last_point, waypoints[-1]):
#                 refined_path.append(intermediate_waypoint)
        
#         if is_closer_to_endpoint(waypoint, last_point, waypoints[-1]):
#             refined_path.append(waypoint)
        
#         last_point = waypoint

#     refined_path = avoid_obstacles(refined_path, obstacles, step_size)
#     return refined_path

# # Ensure waypoints maintain safe clearance from obstacles
# def avoid_obstacles(path, obstacles, step_size):
#     safe_path = []
#     obstacle_clearance = 1.1
#     for idx, point in enumerate(path):
#         safe = True
#         for obs_x, obs_y, obs_z in obstacles:
#             if (obs_x - 1 <= point[0] <= obs_x + 1 and
#                 obs_y - 1 <= point[1] <= obs_y + 1 and
#                 obs_z - 1 <= point[2] <= obs_z + 1):
#                 safe = False
#                 break

#         if safe:
#             safe_path.append(point)
#         else:
#             rospy.loginfo("Point %s is too close to an obstacle. Creating detour...", point)
#             detour_waypoints = create_detour(point, path[idx + 1] if idx + 1 < len(path) else path[-1], obstacles)
#             rospy.loginfo("Detour waypoints created: %s", detour_waypoints)
#             safe_path.extend(detour_waypoints)

#     return safe_path

# # Create a detour to avoid obstacles without backtracking
# def create_detour(start, end, obstacles, clearance=1.1):
#     detour_path = []
#     for obs in obstacles:
#         sx, sy, sz = start
#         ex, ey, ez = end
#         ox, oy, oz = obs
        
#         # Determine primary detour axis based on obstacle position
#         if abs(ex - ox) > abs(ey - oy):
#             if sy < oy:
#                 detour_path.append((sx, oy - clearance, sz))
#             else:
#                 detour_path.append((sx, oy + clearance, sz))
#             detour_path.append((ex, detour_path[-1][1], ez))
#         else:
#             if sx < ox:
#                 detour_path.append((ox - clearance, sy, sz))
#             else:
#                 detour_path.append((ox + clearance, sy, sz))
#             detour_path.append((detour_path[-1][0], ey, ez))

#     return detour_path

# # Execute the trajectory by sending waypoints to the drone
# def execute_trajectory(path_instructions, end_point):
#     pose = PoseStamped()
#     rate = rospy.Rate(20)

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     offb_set_mode = SetModeRequest()
#     offb_set_mode.custom_mode = 'OFFBOARD'
#     arm_cmd = CommandBoolRequest()
#     arm_cmd.value = True

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     # Publish some initial setpoints before starting offboard mode
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         set_mode_client.call(offb_set_mode)
#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         arming_client.call(arm_cmd)

#     # Execute and log each waypoint
#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         x, y, z = waypoint
#         pose.pose.position.x = x
#         pose.pose.position.y = y
#         pose.pose.position.z = z

#         rospy.loginfo("Navigating to waypoint %d: (%.3f, %.3f, %.3f)", idx, x, y, z)
#         for _ in range(10):
#             local_pos_pub.publish(pose)
#             rate.sleep()

#         if waypoint == end_point:
#             break

#     rospy.loginfo("Final waypoint reached. Holding position.")
#     # Hold the final position indefinitely
#     while not rospy.is_shutdown():
#         pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
#         local_pos_pub.publish(pose)
#         rate.sleep()

# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     rospy.loginfo("Drone navigation node started.")

#     # Define start and end points along with obstacles
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.03, -1.5, 0.5),
#         (0.07, -5.06, 0.5)
#     ]
    
#     rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
#     waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     if waypoints:
#         rospy.loginfo("Waypoints received: %s", waypoints)
#         # Ensure the final waypoint matches the endpoint
#         waypoints[-1] = end_point
#         refined_path = generate_smooth_path_with_intermediate_waypoints(waypoints, obstacle_list)
        
#         rospy.loginfo("Final refined path with intermediate waypoints: %s", refined_path)
        
#         execute_trajectory(refined_path, end_point)
#     else:
#         rospy.logerr("No path found to the destination.")


# #!/usr/bin/env python3
# import rospy
# import time
# import re
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# # Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek)
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# current_state = State()

# # Callback to update the current state
# def state_cb(msg):
#     global current_state
#     current_state = msg

# # ROS setup: Subscriber and Publisher
# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)

# # Request navigation instructions from DeepSeek R1 with obstacle detour
# def get_llm_navigation_instructions(start, end, obstacles):
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         f"Provide a list of waypoints for a drone to travel from start {start} to end {end} while avoiding obstacles at: {obstacle_str}. "
#         "The path must be smooth, continuously progress toward the endpoint without backtracking, and the first waypoint must be the start and the last waypoint must be the end. "
#         "Do not include any extra commentary or explanation. "
#         "Return ONLY the list of waypoints in the exact format (x, y, z), with each waypoint on a new line."
#     )
    
#     rospy.loginfo("Sending prompt to DeepSeek model: %s", prompt)
#     try:
#         completion = client.chat.completions.create(
#             model="deepseek-ai/deepseek-r1",  # DeepSeek model endpoint
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.6,
#             top_p=0.7,
#             max_tokens=1024,
#             stream=False  # Using non-streaming mode
#         )
        
#         rospy.loginfo("Raw response from DeepSeek: %s", completion)
        
#         # Check if the response is a raw string or a structured object
#         if isinstance(completion, str):
#             instructions = completion
#         elif hasattr(completion, "choices") and completion.choices:
#             if hasattr(completion.choices[0], "message"):
#                 instructions = completion.choices[0].message.content
#             elif hasattr(completion.choices[0], "text"):
#                 instructions = completion.choices[0].text
#             else:
#                 instructions = ""
#         else:
#             instructions = ""
            
#         rospy.loginfo("Extracted instructions: %s", instructions)
#         waypoints = parse_waypoints(instructions)
#         rospy.loginfo("Parsed waypoints: %s", waypoints)
        
#         # Fallback in case no waypoints were extracted
#         if not waypoints:
#             rospy.logwarn("No waypoints extracted. Using fallback path.")
#             waypoints = [
#                 start,
#                 (0.5, 0.0, 0.5),
#                 (0.5, -3.0, 0.5),
#                 end
#             ]
        
#         return waypoints
    
#     except Exception as e:
#         rospy.logerr("Error fetching navigation instructions: %s", e)
#         # Fallback path in case of error
#         return [
#             start,
#             (0.5, 0.0, 0.5),
#             (0.5, -3.0, 0.5),
#             end
#         ]

# # Parse waypoints from LLM response (expects format: (x, y, z))
# def parse_waypoints(instructions):
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, instructions):
#         waypoint = tuple(map(float, match.groups()))
#         waypoints.append(waypoint)
#     return waypoints

# # Check if the new point is closer to the endpoint than the previous point to prevent backtracking
# def is_closer_to_endpoint(new_point, last_point, endpoint):
#     new_dist = sum((new_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
#     last_dist = sum((last_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
#     return new_dist < last_dist

# # Generate a smooth path that strictly progresses towards the endpoint, avoiding obstacles
# def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
#     refined_path = []
#     last_point = waypoints[0]

#     for waypoint in waypoints:
#         distance = sum((waypoint[i] - last_point[i]) ** 2 for i in range(3)) ** 0.5
#         direction = [(waypoint[i] - last_point[i]) / distance for i in range(3)] if distance > 0 else [0, 0, 0]

#         num_intermediate_steps = int(distance // step_size)
#         for step in range(1, num_intermediate_steps + 1):
#             intermediate_waypoint = tuple(
#                 last_point[i] + direction[i] * step * step_size for i in range(3)
#             )
#             if is_closer_to_endpoint(intermediate_waypoint, last_point, waypoints[-1]):
#                 refined_path.append(intermediate_waypoint)
        
#         if is_closer_to_endpoint(waypoint, last_point, waypoints[-1]):
#             refined_path.append(waypoint)
        
#         last_point = waypoint

#     refined_path = avoid_obstacles(refined_path, obstacles, step_size)
#     return refined_path

# # Ensure waypoints maintain safe clearance from obstacles
# def avoid_obstacles(path, obstacles, step_size):
#     safe_path = []
#     obstacle_clearance = 1.1
#     for idx, point in enumerate(path):
#         safe = True
#         for obs_x, obs_y, obs_z in obstacles:
#             if (obs_x - 1 <= point[0] <= obs_x + 1 and
#                 obs_y - 1 <= point[1] <= obs_y + 1 and
#                 obs_z - 1 <= point[2] <= obs_z + 1):
#                 safe = False
#                 break

#         if safe:
#             safe_path.append(point)
#         else:
#             rospy.loginfo("Point %s is too close to an obstacle. Creating detour...", point)
#             detour_waypoints = create_detour(point, path[idx + 1] if idx + 1 < len(path) else path[-1], obstacles)
#             rospy.loginfo("Detour waypoints created: %s", detour_waypoints)
#             safe_path.extend(detour_waypoints)

#     return safe_path

# # Create a detour to avoid obstacles without backtracking
# def create_detour(start, end, obstacles, clearance=1.1):
#     detour_path = []
#     for obs in obstacles:
#         sx, sy, sz = start
#         ex, ey, ez = end
#         ox, oy, oz = obs
        
#         # Determine primary detour axis based on obstacle position
#         if abs(ex - ox) > abs(ey - oy):
#             if sy < oy:
#                 detour_path.append((sx, oy - clearance, sz))
#             else:
#                 detour_path.append((sx, oy + clearance, sz))
#             detour_path.append((ex, detour_path[-1][1], ez))
#         else:
#             if sx < ox:
#                 detour_path.append((ox - clearance, sy, sz))
#             else:
#                 detour_path.append((ox + clearance, sy, sz))
#             detour_path.append((detour_path[-1][0], ey, ez))

#     return detour_path

# # Execute the trajectory by sending waypoints to the drone
# def execute_trajectory(path_instructions, end_point):
#     pose = PoseStamped()
#     rate = rospy.Rate(20)  # 20 Hz publication rate
#     cycles_per_waypoint = 50  # Number of cycles to send each waypoint

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     offb_set_mode = SetModeRequest()
#     offb_set_mode.custom_mode = 'OFFBOARD'
#     arm_cmd = CommandBoolRequest()
#     arm_cmd.value = True

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     # Publish some initial setpoints before starting offboard mode
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         set_mode_client.call(offb_set_mode)
#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         arming_client.call(arm_cmd)

#     # Execute and log each waypoint
#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         x, y, z = waypoint
#         pose.pose.position.x = x
#         pose.pose.position.y = y
#         pose.pose.position.z = z

#         rospy.loginfo("Navigating to waypoint %d: (%.3f, %.3f, %.3f)", idx, x, y, z)
#         # Repeatedly publish the same waypoint to counteract delays
#         for _ in range(cycles_per_waypoint):
#             local_pos_pub.publish(pose)
#             rate.sleep()

#         if waypoint == end_point:
#             break

#     rospy.loginfo("Final waypoint reached. Holding position.")
#     # Hold the final position indefinitely
#     while not rospy.is_shutdown():
#         pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
#         local_pos_pub.publish(pose)
#         rate.sleep()

# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     rospy.loginfo("Drone navigation node started.")

#     # Define start and end points along with obstacles
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.03, -1.5, 0.5),
#         (0.07, -5.06, 0.5)
#     ]
    
#     rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
#     waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     if waypoints:
#         rospy.loginfo("Waypoints received: %s", waypoints)
#         # Ensure the final waypoint matches the endpoint
#         waypoints[-1] = end_point
#         refined_path = generate_smooth_path_with_intermediate_waypoints(waypoints, obstacle_list)
        
#         rospy.loginfo("Final refined path with intermediate waypoints: %s", refined_path)
        
#         execute_trajectory(refined_path, end_point)
#     else:
#         rospy.logerr("No path found to the destination.")

# #!/usr/bin/env python3
# import rospy
# import time
# import re
# import os
# import logging
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped, Point
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, SetMode

# # Configure Python logging to file in your home directory.
# log_file = os.path.join(os.environ["HOME"], "drone_navigation.log")
# logging.basicConfig(filename=log_file,
#                     level=logging.DEBUG,
#                     format='%(asctime)s - %(levelname)s - %(message)s')

# # Helper logging functions: log to both ROS and file.
# def log_info(msg):
#     rospy.loginfo(msg)
#     logging.info(msg)

# def log_warn(msg):
#     rospy.logwarn(msg)
#     logging.warning(msg)

# def log_err(msg):
#     rospy.logerr(msg)
#     logging.error(msg)

# # Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek)
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# # Global state variables
# current_state = State()
# current_pose = None  # Drone's current position

# # Callback to update drone's state from /mavros/state
# def state_cb(msg):
#     global current_state
#     current_state = msg

# # Callback to update drone's local position from /mavros/local_position/pose
# def pose_cb(msg):
#     global current_pose
#     current_pose = msg.pose.position

# # ROS setup: Subscribers and Publisher
# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)
# rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

# def get_llm_navigation_instructions(start, end, obstacles, max_retries=3, delay_between=2.0):
#     # Modified prompt: instruct model to output ONLY the main waypoints with markers.
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         f"You are a drone path planning assistant. Given:\n"
#         f"Start: {start}\n"
#         f"End: {end}\n"
#         f"Obstacles: {obstacle_str}\n\n"
#         f"Provide ONLY a final list of main waypoints for a smooth path from start to end (no chain-of-thought or commentary). "
#         f"Output EXACTLY as follows:\n\n"
#         f"BEGIN\n"
#         f"(x1, y1, z1)\n"
#         f"(x2, y2, z2)\n"
#         f"...\n"
#         f"(xn, yn, zn)\n"
#         f"END"
#     )
#     log_info("Sending prompt to DeepSeek model:\n%s" % prompt)
    
#     instructions = ""
#     for attempt in range(max_retries):
#         try:
#             completion = client.chat.completions.create(
#                 model="deepseek-ai/deepseek-r1",
#                 messages=[{"role": "user", "content": prompt}],
#                 temperature=0.0,  # Deterministic output
#                 top_p=1.0,
#                 max_tokens=256,
#                 stream=False
#             )
#             log_info("Raw response from DeepSeek (attempt %d): %s" % (attempt+1, completion))
#             if isinstance(completion, str):
#                 instructions = completion
#             elif hasattr(completion, "choices") and completion.choices:
#                 if hasattr(completion.choices[0], "message"):
#                     instructions = completion.choices[0].message.content
#                 elif hasattr(completion.choices[0], "text"):
#                     instructions = completion.choices[0].text
#             else:
#                 instructions = ""
            
#             if instructions.strip():
#                 log_info("Extracted instructions:\n%s" % instructions)
#                 break  # Valid response obtained.
#             else:
#                 log_warn("Empty instructions received on attempt %d." % (attempt+1))
#         except Exception as e:
#             log_err("Error on API call attempt %d: %s" % (attempt+1, e))
#         rospy.sleep(delay_between)
    
#     # Do not use fallback: if no instructions, return an empty list.
#     if not instructions.strip():
#         log_err("No instructions received from DeepSeek after %d attempts." % max_retries)
#         return []
    
#     waypoints = parse_waypoints(instructions)
#     log_info("Parsed waypoints: %s" % waypoints)
#     return waypoints

# def parse_waypoints(instructions):
#     # Extract text between BEGIN and END markers.
#     m = re.search(r"BEGIN(.*)END", instructions, re.DOTALL)
#     if m:
#         content = m.group(1)
#     else:
#         content = instructions
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, content):
#         waypoint = tuple(map(float, match.groups()))
#         waypoints.append(waypoint)
#     return waypoints

# def has_reached_waypoint(target, tolerance=0.3):
#     if current_pose is None:
#         return False
#     dx = current_pose.x - target[0]
#     dy = current_pose.y - target[1]
#     dz = current_pose.z - target[2]
#     distance = (dx**2 + dy**2 + dz**2)**0.5
#     return distance < tolerance

# def smooth_move_to_waypoint(waypoint, pose, rate, tolerance=0.3, max_cycles=300, gain=0.2):
#     cycle_count = 0
#     while not rospy.is_shutdown() and cycle_count < max_cycles:
#         if current_pose is None:
#             rate.sleep()
#             continue
#         dx = waypoint[0] - current_pose.x
#         dy = waypoint[1] - current_pose.y
#         dz = waypoint[2] - current_pose.z
#         error = (dx**2 + dy**2 + dz**2)**0.5
#         if error < tolerance:
#             log_info("Reached waypoint: (%.3f, %.3f, %.3f)" % (waypoint[0], waypoint[1], waypoint[2]))
#             break
#         new_setpoint = (
#             current_pose.x + gain * dx,
#             current_pose.y + gain * dy,
#             current_pose.z + gain * dz
#         )
#         pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = new_setpoint
#         local_pos_pub.publish(pose)
#         rate.sleep()
#         cycle_count += 1

# def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
#     refined_path = []
#     last_point = waypoints[0]
#     for waypoint in waypoints:
#         distance = sum((waypoint[i] - last_point[i])**2 for i in range(3))**0.5
#         num_steps = max(int(distance // step_size), 1)
#         for step in range(1, num_steps + 1):
#             intermediate_waypoint = tuple(
#                 last_point[i] + (waypoint[i] - last_point[i]) * step / num_steps for i in range(3)
#             )
#             refined_path.append(intermediate_waypoint)
#         refined_path.append(waypoint)
#         last_point = waypoint
#     refined_path = avoid_obstacles(refined_path, obstacles, clearance=0.5)
#     return refined_path

# def avoid_obstacles(path, obstacles, clearance=0.5):
#     safe_path = []
#     for point in path:
#         adjusted_point = list(point)
#         for obs in obstacles:
#             if abs(point[0] - obs[0]) < clearance and abs(point[1] - obs[1]) < clearance:
#                 if point[0] >= obs[0]:
#                     adjusted_point[0] = obs[0] + clearance
#                 else:
#                     adjusted_point[0] = obs[0] - clearance
#         safe_path.append(tuple(adjusted_point))
#     return safe_path

# def execute_trajectory(path_instructions, end_point):
#     if not path_instructions:
#         log_err("No path instructions available; aborting trajectory execution.")
#         return

#     pose = PoseStamped()
#     rate = rospy.Rate(20)  # 20 Hz publication rate
#     tolerance = 0.3         # meters
#     max_cycles = 300
#     stabilization_time = 1.0  # seconds

#     log_info("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     offb_set_mode = SetMode()
#     offb_set_mode.custom_mode = 'OFFBOARD'
#     arm_cmd = CommandBool()
#     arm_cmd.value = True

#     log_info("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     log_info("FCU connected, publishing initial setpoints...")
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     if current_state.mode != "OFFBOARD":
#         log_info("Setting OFFBOARD mode...")
#         set_mode_client.call(offb_set_mode)
#     if not current_state.armed:
#         log_info("Arming the drone...")
#         arming_client.call(arm_cmd)

#     log_info("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         log_info("Moving toward waypoint %d: (%.3f, %.3f, %.3f)" % (idx, waypoint[0], waypoint[1], waypoint[2]))
#         smooth_move_to_waypoint(waypoint, pose, rate, tolerance, max_cycles, gain=0.2)
#         log_info("Waypoint %d reached. Stabilizing..." % idx)
#         rospy.sleep(stabilization_time)
#         if waypoint == end_point:
#             break

#     log_info("Final waypoint reached. Holding position.")
#     while not rospy.is_shutdown():
#         pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
#         local_pos_pub.publish(pose)
#         rate.sleep()

# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     log_info("Drone navigation node started.")

#     # Define start and end points and obstacles (static obstacles as (x, y, z))
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.03, -1.5, 0.5),
#         (0.07, -5.06, 0.5)
#     ]
    
#     log_info("Requesting navigation instructions from DeepSeek model...")
#     waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     log_info("Waypoints received: %s" % waypoints)
#     # Ensure the final waypoint matches the endpoint
#     if waypoints:
#         waypoints[-1] = end_point
#         refined_path = generate_smooth_path_with_intermediate_waypoints(waypoints, obstacle_list, step_size=0.1)
#         log_info("Final refined path with intermediate waypoints: %s" % refined_path)
#         execute_trajectory(refined_path, end_point)
#     else:
#         log_err("No waypoints received from DeepSeek; aborting mission.")








# #!/usr/bin/env python3
# import rospy
# import time
# import re
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped, Point
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

# # Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek)
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# # Global state variables
# current_state = State()
# current_pose = None  # Drone's actual position

# # Callback to update drone's state (from mavros/state)
# def state_cb(msg):
#     global current_state
#     current_state = msg

# # Callback to update drone's local position (from mavros/local_position/pose)
# def pose_cb(msg):
#     global current_pose
#     current_pose = msg.pose.position

# # ROS setup: Subscribers and Publisher
# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)
# rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

# # Request navigation instructions from DeepSeek
# def get_llm_navigation_instructions(start, end, obstacles):
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         f"Provide a list of waypoints for a drone to travel from start {start} to end {end} while avoiding obstacles at: {obstacle_str}. "
#         "The path must be smooth and continuously progress toward the endpoint without backtracking. "
#         "The first waypoint must be the start and the last must be the end. "
#         "Do not include any commentary or explanation. "
#         "Return ONLY the list of waypoints in the exact format (x, y, z), with each waypoint on a new line."
#     )
    
#     rospy.loginfo("Sending prompt to DeepSeek model: %s", prompt)
#     try:
#         completion = client.chat.completions.create(
#             model="deepseek-ai/deepseek-r1",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.6,
#             top_p=0.7,
#             max_tokens=1024,
#             stream=False
#         )
        
#         rospy.loginfo("Raw response from DeepSeek: %s", completion)
        
#         if isinstance(completion, str):
#             instructions = completion
#         elif hasattr(completion, "choices") and completion.choices:
#             if hasattr(completion.choices[0], "message"):
#                 instructions = completion.choices[0].message.content
#             elif hasattr(completion.choices[0], "text"):
#                 instructions = completion.choices[0].text
#             else:
#                 instructions = ""
#         else:
#             instructions = ""
            
#         rospy.loginfo("Extracted instructions: %s", instructions)
#         waypoints = parse_waypoints(instructions)
#         rospy.loginfo("Parsed waypoints: %s", waypoints)
        
#         # Fallback path if no waypoints were parsed
#         if not waypoints:
#             rospy.logwarn("No waypoints extracted. Using fallback path.")
#             waypoints = [
#                 start,
#                 (0.5, 0.0, 0.5),
#                 (0.5, -3.0, 0.5),
#                 end
#             ]
#         return waypoints
    
#     except Exception as e:
#         rospy.logerr("Error fetching navigation instructions: %s", e)
#         return [
#             start,
#             (0.5, 0.0, 0.5),
#             (0.5, -3.0, 0.5),
#             end
#         ]

# # Parse waypoints from the response (expects format: (x, y, z))
# def parse_waypoints(instructions):
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, instructions):
#         waypoint = tuple(map(float, match.groups()))
#         waypoints.append(waypoint)
#     return waypoints

# # Check if a point is close enough to the target waypoint
# def has_reached_waypoint(target, tolerance=0.3):
#     if current_pose is None:
#         return False
#     dx = current_pose.x - target[0]
#     dy = current_pose.y - target[1]
#     dz = current_pose.z - target[2]
#     distance = (dx**2 + dy**2 + dz**2)**0.5
#     return distance < tolerance

# # Generate a smooth path with intermediate waypoints (and avoid obstacles)
# def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
#     refined_path = []
#     last_point = waypoints[0]
#     for waypoint in waypoints:
#         distance = sum((waypoint[i] - last_point[i])**2 for i in range(3))**0.5
#         direction = [(waypoint[i] - last_point[i]) / distance for i in range(3)] if distance > 0 else [0, 0, 0]
#         num_intermediate_steps = int(distance // step_size)
#         for step in range(1, num_intermediate_steps + 1):
#             intermediate_waypoint = tuple(
#                 last_point[i] + direction[i] * step * step_size for i in range(3)
#             )
#             refined_path.append(intermediate_waypoint)
#         refined_path.append(waypoint)
#         last_point = waypoint
#     refined_path = avoid_obstacles(refined_path, obstacles, step_size)
#     return refined_path

# # Adjust the path to avoid obstacles
# def avoid_obstacles(path, obstacles, step_size):
#     safe_path = []
#     for idx, point in enumerate(path):
#         safe = True
#         for obs_x, obs_y, obs_z in obstacles:
#             if (obs_x - 1 <= point[0] <= obs_x + 1 and
#                 obs_y - 1 <= point[1] <= obs_y + 1 and
#                 obs_z - 1 <= point[2] <= obs_z + 1):
#                 safe = False
#                 break
#         if safe:
#             safe_path.append(point)
#         else:
#             rospy.loginfo("Point %s is too close to an obstacle. Creating detour...", point)
#             detour_waypoints = create_detour(point, path[idx+1] if idx+1 < len(path) else path[-1], obstacles)
#             rospy.loginfo("Detour waypoints: %s", detour_waypoints)
#             safe_path.extend(detour_waypoints)
#     return safe_path

# # Create a detour path around an obstacle
# def create_detour(start, end, obstacles, clearance=1.1):
#     detour_path = []
#     for obs in obstacles:
#         sx, sy, sz = start
#         ex, ey, ez = end
#         ox, oy, oz = obs
#         if abs(ex - ox) > abs(ey - oy):
#             if sy < oy:
#                 detour_path.append((sx, oy - clearance, sz))
#             else:
#                 detour_path.append((sx, oy + clearance, sz))
#             detour_path.append((ex, detour_path[-1][1], ez))
#         else:
#             if sx < ox:
#                 detour_path.append((ox - clearance, sy, sz))
#             else:
#                 detour_path.append((ox + clearance, sy, sz))
#             detour_path.append((detour_path[-1][0], ey, ez))
#     return detour_path

# # Execute the trajectory by repeatedly sending the same waypoint until it is reached
# def execute_trajectory(path_instructions, end_point):
#     pose = PoseStamped()
#     rate = rospy.Rate(20)  # 20 Hz publication rate
#     max_cycles = 200     # Maximum cycles to try per waypoint
#     tolerance = 0.3      # Distance tolerance (meters)

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     offb_set_mode = SetModeRequest()
#     offb_set_mode.custom_mode = 'OFFBOARD'
#     arm_cmd = CommandBoolRequest()
#     arm_cmd.value = True

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         set_mode_client.call(offb_set_mode)
#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         arming_client.call(arm_cmd)

#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         x, y, z = waypoint
#         pose.pose.position.x = x
#         pose.pose.position.y = y
#         pose.pose.position.z = z
#         rospy.loginfo("Navigating to waypoint %d: (%.3f, %.3f, %.3f)", idx, x, y, z)
#         cycle_count = 0
#         while not rospy.is_shutdown() and cycle_count < max_cycles:
#             local_pos_pub.publish(pose)
#             rate.sleep()
#             cycle_count += 1
#             if has_reached_waypoint(waypoint, tolerance):
#                 rospy.loginfo("Waypoint %d reached", idx)
#                 break

#         # Optionally, add a short pause here if needed
#         if waypoint == end_point:
#             break

#     rospy.loginfo("Final waypoint reached. Holding position.")
#     while not rospy.is_shutdown():
#         pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
#         local_pos_pub.publish(pose)
#         rate.sleep()

# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     rospy.loginfo("Drone navigation node started.")

#     # Define start/end points and obstacles
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.03, -1.5, 0.5),
#         (0.07, -5.06, 0.5)
#     ]
    
#     rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
#     waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     if waypoints:
#         rospy.loginfo("Waypoints received: %s", waypoints)
#         waypoints[-1] = end_point
#         refined_path = generate_smooth_path_with_intermediate_waypoints(waypoints, obstacle_list)
#         rospy.loginfo("Final refined path with intermediate waypoints: %s", refined_path)
#         execute_trajectory(refined_path, end_point)
#     else:
#         rospy.logerr("No path found to the destination.")

#!/usr/bin/env python3
import rospy
import time
import re
from openai import OpenAI
from geometry_msgs.msg import PoseStamped, Point
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode

# Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek R1)
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

# Global state variables
current_state = State()
current_pose = None  # Drone's current position

def state_cb(msg):
    global current_state
    current_state = msg

def pose_cb(msg):
    global current_pose
    current_pose = msg.pose.position

local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
rospy.Subscriber("mavros/state", State, state_cb)
rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

def get_llm_navigation_instructions(start, end, obstacles, max_retries=3, delay_between=2.0):
    # Prepare obstacle string and the prompt instructing the model to provide ONLY main waypoints.
    obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
    prompt = (
        "You are a drone path planning assistant. Provide ONLY the final list of main waypoints for a smooth path "
        "from start to end. The path must begin at the start and end at the end, and progress smoothly without backtracking. "
        "Output the answer EXACTLY in the following format (each waypoint on a new line):\n\n"
        "BEGIN\n"
        "(x1, y1, z1)\n"
        "(x2, y2, z2)\n"
        "...\n"
        "(xn, yn, zn)\n"
        "END\n\n"
        f"Start: {start}\n"
        f"End: {end}\n"
        f"Obstacles: {obstacle_str}\n"
        "Do not include any additional commentary or chain-of-thought in your output."
    )
    rospy.loginfo("Sending prompt to DeepSeek model:\n%s", prompt)
    
    instructions = ""
    full_response = ""  # To capture the complete API output including any chain-of-thought.
    for attempt in range(max_retries):
        try:
            # Removed the 'stop' parameter so the full response is captured.
            completion = client.chat.completions.create(
                model="deepseek-ai/deepseek-r1",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,   # Deterministic output
                top_p=1.0,
                max_tokens=256,
                stream=False
            )
            # Log the complete raw API response (including any chain-of-thought)
            rospy.loginfo("Full API raw response (attempt %d): %s", attempt+1, completion)
            full_response = str(completion)
            
            # Extract the main instructions from the API response.
            if isinstance(completion, str):
                instructions = completion
            elif hasattr(completion, "choices") and completion.choices:
                if hasattr(completion.choices[0], "message"):
                    instructions = completion.choices[0].message.content
                elif hasattr(completion.choices[0], "text"):
                    instructions = completion.choices[0].text
            else:
                instructions = ""
            
            rospy.loginfo("Extracted instructions:\n%s", instructions)
            if instructions.strip():
                break
            else:
                rospy.logwarn("Empty instructions received on attempt %d.", attempt+1)
        except Exception as e:
            rospy.logerr("Error on API call attempt %d: %s", attempt+1, e)
        rospy.sleep(delay_between)
    
    if not instructions.strip():
        rospy.logerr("No instructions received from DeepSeek after %d attempts. Aborting.", max_retries)
        return []  # No fallback; abort if no valid response.
    
    # Log the full raw response (chain-of-thought included) for debugging.
    rospy.loginfo("Complete API response (including any chain-of-thought):\n%s", full_response)
    
    waypoints = parse_waypoints(instructions)
    rospy.loginfo("Parsed waypoints: %s", waypoints)
    
    if not waypoints:
        rospy.logerr("Failed to parse valid waypoints from the API response. Aborting.")
        return []  # Aborting if no valid waypoints.
    return waypoints

def parse_waypoints(instructions):
    """
    Extract text between the BEGIN and END markers. If not found, try to extract any waypoint-like tuples.
    """
    m = re.search(r"BEGIN(.*)END", instructions, re.DOTALL)
    if m:
        content = m.group(1)
    else:
        content = instructions
    waypoints = []
    pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
    for match in re.finditer(pattern, content):
        try:
            waypoint = tuple(map(float, match.groups()))
            waypoints.append(waypoint)
        except ValueError:
            continue
    return waypoints

def has_reached_waypoint(target, tolerance=0.3):
    if current_pose is None:
        return False
    dx = current_pose.x - target[0]
    dy = current_pose.y - target[1]
    dz = current_pose.z - target[2]
    distance = (dx**2 + dy**2 + dz**2)**0.5
    return distance < tolerance

def smooth_move_to_waypoint(waypoint, pose, rate, tolerance=0.3, max_cycles=300, gain=0.2):
    cycle_count = 0
    while not rospy.is_shutdown() and cycle_count < max_cycles:
        if current_pose is None:
            rate.sleep()
            continue
        dx = waypoint[0] - current_pose.x
        dy = waypoint[1] - current_pose.y
        dz = waypoint[2] - current_pose.z
        error = (dx**2 + dy**2 + dz**2)**0.5
        if error < tolerance:
            rospy.loginfo("Reached waypoint: (%.3f, %.3f, %.3f)", waypoint[0], waypoint[1], waypoint[2])
            break
        new_setpoint = (
            current_pose.x + gain * dx,
            current_pose.y + gain * dy,
            current_pose.z + gain * dz
        )
        pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = new_setpoint
        local_pos_pub.publish(pose)
        rate.sleep()
        cycle_count += 1

def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
    refined_path = []
    last_point = waypoints[0]
    for waypoint in waypoints:
        distance = sum((waypoint[i] - last_point[i])**2 for i in range(3))**0.5
        num_steps = max(int(distance // step_size), 1)
        for step in range(1, num_steps + 1):
            intermediate_waypoint = tuple(
                last_point[i] + (waypoint[i] - last_point[i]) * step / num_steps for i in range(3)
            )
            refined_path.append(intermediate_waypoint)
        refined_path.append(waypoint)
        last_point = waypoint
    refined_path = avoid_obstacles(refined_path, obstacles, clearance=0.5)
    return refined_path

def avoid_obstacles(path, obstacles, clearance=0.5):
    safe_path = []
    for point in path:
        adjusted_point = list(point)
        for obs in obstacles:
            if abs(point[0] - obs[0]) < clearance and abs(point[1] - obs[1]) < clearance:
                if point[0] >= obs[0]:
                    adjusted_point[0] = obs[0] + clearance
                else:
                    adjusted_point[0] = obs[0] - clearance
        safe_path.append(tuple(adjusted_point))
    return safe_path

def execute_trajectory(path_instructions, end_point):
    if not path_instructions:
        rospy.logerr("No path instructions available; aborting trajectory execution.")
        return

    pose = PoseStamped()
    rate = rospy.Rate(20)  # 20 Hz publication rate
    tolerance = 0.3         # meters
    max_cycles = 300
    stabilization_time = 1.0  # seconds

    rospy.loginfo("Waiting for MAVROS services to be available...")
    rospy.wait_for_service("/mavros/cmd/arming")
    arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
    rospy.wait_for_service("/mavros/set_mode")
    set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

    offb_set_mode = SetMode()
    offb_set_mode.custom_mode = 'OFFBOARD'
    arm_cmd = CommandBool()
    arm_cmd.value = True

    rospy.loginfo("Waiting for FCU connection...")
    while not rospy.is_shutdown() and not current_state.connected:
        rate.sleep()

    rospy.loginfo("FCU connected, publishing initial setpoints...")
    for _ in range(200):
        local_pos_pub.publish(pose)
        rate.sleep()

    if current_state.mode != "OFFBOARD":
        rospy.loginfo("Setting OFFBOARD mode...")
        set_mode_client.call(offb_set_mode)
    if not current_state.armed:
        rospy.loginfo("Arming the drone...")
        arming_client.call(arm_cmd)

    rospy.loginfo("Starting trajectory execution...")
    for idx, waypoint in enumerate(path_instructions):
        rospy.loginfo("Moving toward waypoint %d: (%.3f, %.3f, %.3f)", idx, waypoint[0], waypoint[1], waypoint[2])
        smooth_move_to_waypoint(waypoint, pose, rate, tolerance, max_cycles, gain=0.2)
        rospy.loginfo("Waypoint %d reached. Stabilizing...", idx)
        rospy.sleep(stabilization_time)
        if waypoint == end_point:
            break

    rospy.loginfo("Final waypoint reached. Holding position.")
    while not rospy.is_shutdown():
        pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
        local_pos_pub.publish(pose)
        rate.sleep()

if __name__ == "__main__":
    rospy.init_node("drone_navigation_node")
    rospy.loginfo("Drone navigation node started.")

    # Define start and end points and obstacles
    start_point = (0.0, 1.0, 0.5)
    end_point = (0.0, -6.5, 0.5)
    obstacle_list = [
        (0.03, -1.5, 0.5),
        (0.07, -5.06, 0.5)
    ]
    
    rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
    waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
    rospy.loginfo("Waypoints received: %s", waypoints)
    if waypoints:
        # Ensure the final waypoint exactly matches the end point.
        waypoints[-1] = end_point
        refined_path = generate_smooth_path_with_intermediate_waypoints(waypoints, obstacle_list, step_size=0.1)
        rospy.loginfo("Final refined path with intermediate waypoints: %s", refined_path)
        execute_trajectory(refined_path, end_point)
    else:
        rospy.logerr("No valid waypoints received from DeepSeek; aborting mission.")
