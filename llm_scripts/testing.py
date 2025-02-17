# #!/usr/bin/env python3
# import rospy
# import time
# import re
# from math import sqrt
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped, Point
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, SetMode

# # ---------------------------
# # Initialize DeepSeek Client
# # ---------------------------
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# # ---------------------------
# # Global State Variables
# # ---------------------------
# current_state = State()
# current_pose = None  # Drone's current position

# # ---------------------------
# # ROS Callbacks
# # ---------------------------
# def state_cb(msg):
#     global current_state
#     current_state = msg

# def pose_cb(msg):
#     global current_pose
#     current_pose = msg.pose.position

# # ---------------------------
# # ROS Publishers & Subscribers
# # ---------------------------
# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)
# rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

# # ---------------------------
# # (Optional) LLM Query & Parsing Functions
# # ---------------------------
# def get_llm_navigation_instructions(start, end, obstacles, max_retries=3, delay_between=5.0):
#     """
#     Request main waypoints from DeepSeek.
#     (Note: The current LLM response includes extra chain-of-thought.
#     In our revised approach we ignore the extra points and use a direct path.)
#     """
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         "Your answer must follow these instructions EXACTLY:\n"
#         "1. The path must start at the 'Start' point and end at the 'End' point.\n"
#         "2. The path must avoid all obstacles completely. Do not include any waypoint that is at or too near an obstacle.\n"
#         "3. Do not include any chain-of-thought, reasoning, or additional commentary.\n"
#         "4. Output EXACTLY in the following format with nothing else:\n\n"
#         "BEGIN\n"
#         "(x1, y1, z1)\n"
#         "(x2, y2, z2)\n"
#         "...\n"
#         "(xn, yn, zn)\n"
#         "END\n\n"
#         f"Start: {start}\n"
#         f"End: {end}\n"
#         f"Obstacles: {obstacle_str}\n"
#         "Do not include any extra text."
#     )
#     rospy.loginfo("Sending prompt to DeepSeek model:\n%s", prompt)
    
#     instructions = ""
#     for attempt in range(max_retries):
#         try:
#             completion = client.chat.completions.create(
#                 model="deepseek-ai/deepseek-r1",
#                 messages=[
#                     {"role": "system", "content": "You are a drone path planning assistant. Do not include any chain-of-thought or commentary. Your output must include only the final list of waypoints exactly between the markers 'BEGIN' and 'END'."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=0.0,
#                 top_p=1.0,
#                 max_tokens=150,
#                 stream=False
#             )
#             rospy.loginfo("API Response Received (Attempt %d): %s", attempt + 1, completion)
            
#             if hasattr(completion, "choices") and completion.choices:
#                 if hasattr(completion.choices[0], "message"):
#                     instructions = completion.choices[0].message.content
#                 elif hasattr(completion.choices[0], "text"):
#                     instructions = completion.choices[0].text
            
#             if instructions.strip():
#                 break
#             else:
#                 rospy.logwarn("Empty instructions received on attempt %d.", attempt + 1)
#         except Exception as e:
#             rospy.logerr("Error on API call attempt %d: %s", attempt + 1, e)
#             if "429" in str(e):
#                 rospy.logwarn("Rate limit exceeded. Waiting before retrying...")
#                 rospy.sleep(10.0)
#         rospy.sleep(delay_between)
    
#     if not instructions.strip():
#         rospy.logerr("No instructions received after %d attempts. Using fallback waypoints.", max_retries)
#         return [start, end]
    
#     waypoints = parse_waypoints(instructions)
#     rospy.loginfo("Parsed main waypoints: %s", waypoints)
    
#     if not waypoints:
#         rospy.logerr("Failed to parse valid waypoints. Using fallback (straight line).")
#         return [start, end]
    
#     return waypoints

# def parse_waypoints(instructions):
#     """Extract coordinate tuples from the text (scanning for tuples)."""
#     begin_marker = "BEGIN"
#     end_marker = "END"
#     start_index = instructions.find(begin_marker)
#     end_index = instructions.find(end_marker, start_index)
#     if start_index != -1 and end_index != -1:
#         relevant_text = instructions[start_index + len(begin_marker):end_index].strip()
#     else:
#         rospy.logwarn("BEGIN/END markers not found. Extracting coordinates from entire response.")
#         relevant_text = instructions

#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, relevant_text):
#         try:
#             waypoint = tuple(map(float, match.groups()))
#             waypoints.append(waypoint)
#         except ValueError:
#             continue
#     return waypoints

# # ---------------------------
# # NEW: Direct Path Generation & Obstacle Adjustment
# # ---------------------------
# def generate_direct_path(start, end, step_size=1.0):
#     """
#     Generate a list of points along the straight line from start to end,
#     with each consecutive point approximately step_size apart.
#     """
#     dx = end[0] - start[0]
#     dy = end[1] - start[1]
#     dz = end[2] - start[2]
#     dist = sqrt(dx**2 + dy**2 + dz**2)
#     num_steps = max(int(dist / step_size), 1)
#     path = []
#     for i in range(num_steps + 1):
#         fraction = i / float(num_steps)
#         point = (start[0] + fraction * dx,
#                  start[1] + fraction * dy,
#                  start[2] + fraction * dz)
#         path.append(point)
#     return path

# def adjust_path_for_obstacles(path, obstacles, clearance=1.1):
#     """
#     Check each point in the direct path. If a point is too close to any obstacle,
#     shift it away along the vector from the obstacle to the point.
#     """
#     adjusted = []
#     for point in path:
#         new_point = point
#         for obs in obstacles:
#             d = sqrt((point[0]-obs[0])**2 + (point[1]-obs[1])**2 + (point[2]-obs[2])**2)
#             if d < clearance:
#                 # Compute the normalized vector from obstacle to point.
#                 if d == 0:
#                     # If exactly at the obstacle center, use an arbitrary offset.
#                     new_point = (point[0] + clearance, point[1], point[2])
#                 else:
#                     diff = (point[0]-obs[0], point[1]-obs[1], point[2]-obs[2])
#                     factor = (clearance - d) / d
#                     new_point = (point[0] + diff[0] * factor,
#                                  point[1] + diff[1] * factor,
#                                  point[2] + diff[2] * factor)
#                 # (Assume one obstacle per point is enough to adjust.)
#                 break
#         adjusted.append(new_point)
#     return adjusted

# def compute_path(start, end, obstacles, step_size=1.0, clearance=1.1):
#     """
#     Compute the desired path from start to end:
#       1. Generate a direct straight-line path (uniformly spaced).
#       2. Adjust any points that are too close to obstacles.
#     """
#     direct = generate_direct_path(start, end, step_size)
#     refined = adjust_path_for_obstacles(direct, obstacles, clearance)
#     return refined

# # ---------------------------
# # Drone Motion Functions (unchanged)
# # ---------------------------
# def has_reached_waypoint(target, tolerance=0.3):
#     if current_pose is None:
#         return False
#     dx = current_pose.x - target[0]
#     dy = current_pose.y - target[1]
#     dz = current_pose.z - target[2]
#     return sqrt(dx**2 + dy**2 + dz**2) < tolerance

# def smooth_move_to_waypoint(waypoint, pose, rate, tolerance=0.3, max_cycles=300, gain=0.2):
#     cycle_count = 0
#     while not rospy.is_shutdown() and cycle_count < max_cycles:
#         if current_pose is None:
#             rate.sleep()
#             continue
#         dx = waypoint[0] - current_pose.x
#         dy = waypoint[1] - current_pose.y
#         dz = waypoint[2] - current_pose.z
#         error = sqrt(dx**2 + dy**2 + dz**2)
#         if error < tolerance:
#             rospy.loginfo("Reached waypoint: (%.3f, %.3f, %.3f)", waypoint[0], waypoint[1], waypoint[2])
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

# def execute_trajectory(path_instructions, end_point):
#     pose = PoseStamped()
#     rate = rospy.Rate(20)  # 20 Hz
#     tolerance = 0.3
#     max_cycles = 300
#     stabilization_time = 1.0

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         try:
#             set_mode_response = set_mode_client(base_mode=0, custom_mode="OFFBOARD")
#             if set_mode_response.mode_sent:
#                 rospy.loginfo("OFFBOARD mode enabled.")
#             else:
#                 rospy.logerr("Failed to set OFFBOARD mode.")
#         except Exception as e:
#             rospy.logerr("Service call failed: %s", e)

#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         try:
#             arming_response = arming_client(value=True)
#             if arming_response.success:
#                 rospy.loginfo("Drone armed.")
#             else:
#                 rospy.logerr("Failed to arm the drone.")
#         except Exception as e:
#             rospy.logerr("Service call failed: %s", e)

#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         rospy.loginfo("Navigating to waypoint %d: (%.3f, %.3f, %.3f)", idx, waypoint[0], waypoint[1], waypoint[2])
#         smooth_move_to_waypoint(waypoint, pose, rate, tolerance, max_cycles, gain=0.2)
#         rospy.loginfo("Waypoint %d reached. Stabilizing...", idx)
#         rospy.sleep(stabilization_time)
#         if waypoint == end_point:
#             break

#     rospy.loginfo("Final waypoint reached. Holding position.")
#     while not rospy.is_shutdown():
#         pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
#         local_pos_pub.publish(pose)
#         rate.sleep()

# # ---------------------------
# # Main Execution
# # ---------------------------
# if __name__ == "__main__":
#     rospy.init_node("drone_navigation_node")
#     rospy.loginfo("Drone navigation node started.")

#     # Define mission parameters
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.0, -1.5, 0.5),
#         (0.01, -5.51, 0.5),
#         (-2.5, -3.5182, 0.5)
#     ]
    
#     # Instead of using the messy LLM output, we compute a direct (shortest) path
#     # with uniform spacing and detour adjustments only when needed.
#     step_size = 1.0    # Adjust as needed for fewer waypoints
#     clearance = 1.1    # Minimum safe distance from any obstacle
#     refined_path = compute_path(start_point, end_point, obstacle_list, step_size, clearance)
    
#     rospy.loginfo("Final refined path with uniform spacing and detours:")
#     for idx, point in enumerate(refined_path):
#         rospy.loginfo("Waypoint %d: %s", idx, point)
    
#     execute_trajectory(refined_path, end_point)









#!/usr/bin/env python3
import rospy
import time
import re
from math import sqrt
from openai import OpenAI
from geometry_msgs.msg import PoseStamped, Point
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode

# ---------------------------
# Initialize DeepSeek Client
# ---------------------------
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

# ---------------------------
# Global State Variables
# ---------------------------
current_state = State()
current_pose = None  # Drone's current position

# ---------------------------
# ROS Callbacks
# ---------------------------
def state_cb(msg):
    global current_state
    current_state = msg

def pose_cb(msg):
    global current_pose
    current_pose = msg.pose.position

# ---------------------------
# ROS Publishers & Subscribers
# ---------------------------
local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
rospy.Subscriber("mavros/state", State, state_cb)
rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

# ---------------------------
# LLM Query & Parsing Functions
# ---------------------------
def get_llm_navigation_instructions(start, end, obstacles, max_retries=3, delay_between=5.0):
    """
    Request main waypoints from DeepSeek. The LLM is instructed to output a final list 
    between the markers BEGIN and END with no extra commentary.
    """
    obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
    prompt = (
        "Your answer must follow these instructions EXACTLY:\n"
        "1. The path must start at the 'Start' point and end at the 'End' point.\n"
        "2. The path must avoid all obstacles completely. Do not include any waypoint that is at or too near an obstacle.\n"
        "3. Do not include any chain-of-thought, reasoning, or additional commentary.\n"
        "4. Output EXACTLY in the following format with nothing else:\n\n"
        "BEGIN\n"
        "(x1, y1, z1)\n"
        "(x2, y2, z2)\n"
        "...\n"
        "(xn, yn, zn)\n"
        "END\n\n"
        f"Start: {start}\n"
        f"End: {end}\n"
        f"Obstacles: {obstacle_str}\n"
        "Do not include any extra text."
    )
    rospy.loginfo("Sending prompt to DeepSeek model:\n%s", prompt)
    
    instructions = ""
    for attempt in range(max_retries):
        try:
            # System message helps enforce the strict format.
            completion = client.chat.completions.create(
                model="deepseek-ai/deepseek-r1",
                messages=[
                    {"role": "system", "content": "You are a drone path planning assistant. Do not include any chain-of-thought or commentary. Your output must include only the final list of waypoints exactly between the markers 'BEGIN' and 'END'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                top_p=1.0,
                max_tokens=150,
                stream=False
            )
            rospy.loginfo("API Response Received (Attempt %d): %s", attempt + 1, completion)
            
            if hasattr(completion, "choices") and completion.choices:
                if hasattr(completion.choices[0], "message"):
                    instructions = completion.choices[0].message.content
                elif hasattr(completion.choices[0], "text"):
                    instructions = completion.choices[0].text
            
            if instructions.strip():
                break
            else:
                rospy.logwarn("Empty instructions received on attempt %d.", attempt + 1)
        except Exception as e:
            rospy.logerr("Error on API call attempt %d: %s", attempt + 1, e)
            if "429" in str(e):
                rospy.logwarn("Rate limit exceeded. Waiting before retrying...")
                rospy.sleep(10.0)
        rospy.sleep(delay_between)
    
    if not instructions.strip():
        rospy.logerr("No instructions received after %d attempts. Using fallback waypoints.", max_retries)
        return [start, end]
    
    waypoints = parse_waypoints(instructions)
    rospy.loginfo("Parsed main waypoints: %s", waypoints)
    
    if not waypoints:
        rospy.logerr("Failed to parse valid waypoints. Using fallback (straight line).")
        return [start, end]
    
    return waypoints

def parse_waypoints(instructions):
    """
    Extract coordinate tuples from text. If the BEGIN/END markers are not found,
    the entire response is scanned for tuples.
    """
    begin_marker = "BEGIN"
    end_marker = "END"
    start_index = instructions.find(begin_marker)
    end_index = instructions.find(end_marker, start_index)
    if start_index != -1 and end_index != -1:
        relevant_text = instructions[start_index + len(begin_marker):end_index].strip()
    else:
        rospy.logwarn("BEGIN/END markers not found. Extracting coordinates from entire response.")
        relevant_text = instructions

    waypoints = []
    pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
    for match in re.finditer(pattern, relevant_text):
        try:
            waypoint = tuple(map(float, match.groups()))
            waypoints.append(waypoint)
        except ValueError:
            continue
    return waypoints

# ---------------------------
# Refined Path Generation Functions
# ---------------------------
def is_closer_to_endpoint(new_point, last_point, endpoint):
    """
    Check if new_point is closer to the endpoint than last_point.
    """
    new_dist = sqrt((new_point[0] - endpoint[0])**2 +
                    (new_point[1] - endpoint[1])**2 +
                    (new_point[2] - endpoint[2])**2)
    last_dist = sqrt((last_point[0] - endpoint[0])**2 +
                     (last_point[1] - endpoint[1])**2 +
                     (last_point[2] - endpoint[2])**2)
    return new_dist < last_dist

def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
    """
    Starting from the LLM-generated main waypoints, create a smooth path by adding
    intermediate points. Then, pass the refined path through obstacle avoidance.
    """
    refined_path = []
    last_point = waypoints[0]
    refined_path.append(last_point)
    
    for waypoint in waypoints[1:]:
        dx = waypoint[0] - last_point[0]
        dy = waypoint[1] - last_point[1]
        dz = waypoint[2] - last_point[2]
        dist = sqrt(dx**2 + dy**2 + dz**2)
        if dist == 0:
            continue
        direction = (dx/dist, dy/dist, dz/dist)
        num_intermediate_steps = int(dist // step_size)
        for step in range(1, num_intermediate_steps + 1):
            intermediate_point = (
                last_point[0] + direction[0] * step * step_size,
                last_point[1] + direction[1] * step * step_size,
                last_point[2] + direction[2] * step * step_size
            )
            if is_closer_to_endpoint(intermediate_point, last_point, waypoints[-1]):
                refined_path.append(intermediate_point)
        if is_closer_to_endpoint(waypoint, last_point, waypoints[-1]):
            refined_path.append(waypoint)
        last_point = waypoint
    
    refined_path = avoid_obstacles(refined_path, obstacles, step_size)
    return refined_path

def avoid_obstacles(path, obstacles, step_size):
    """
    Check each point in the path. If a point is inside a 2x2x2 obstacle block 
    (centered at each obstacle coordinate), then create a detour for that segment.
    """
    safe_path = []
    obstacle_clearance = 1.1  # Adjust clearance as needed
    for idx, point in enumerate(path):
        safe = True
        for obs in obstacles:
            if (obs[0] - 1 <= point[0] <= obs[0] + 1 and
                obs[1] - 1 <= point[1] <= obs[1] + 1 and
                obs[2] - 1 <= point[2] <= obs[2] + 1):
                safe = False
                break
        if safe:
            safe_path.append(point)
        else:
            # If unsafe and a next point exists, generate a detour
            next_point = path[idx+1] if idx+1 < len(path) else path[-1]
            detour_points = create_detour(point, next_point, obstacles, clearance=obstacle_clearance)
            safe_path.extend(detour_points)
    return safe_path

def create_detour(start, end, obstacles, clearance=1.1):
    """
    Create detour waypoints between start and end to bypass obstacles.
    This example creates a simple two-step detour by shifting along either the x or y axis,
    depending on which difference is larger.
    """
    detour_path = []
    sx, sy, sz = start
    ex, ey, ez = end
    # Process each obstacle in turn (if more than one, several detours might be generated)
    for obs in obstacles:
        ox, oy, oz = obs
        if abs(ex - ox) > abs(ey - oy):
            # Prefer a y detour
            if sy < oy:
                detour_path.append((sx, oy - clearance, sz))
            else:
                detour_path.append((sx, oy + clearance, sz))
            detour_path.append((ex, detour_path[-1][1], ez))
        else:
            # Prefer an x detour
            if sx < ox:
                detour_path.append((ox - clearance, sy, sz))
            else:
                detour_path.append((ox + clearance, sy, sz))
            detour_path.append((detour_path[-1][0], ey, ez))
    return detour_path

# ---------------------------
# Drone Motion Functions
# ---------------------------
def has_reached_waypoint(target, tolerance=0.3):
    if current_pose is None:
        return False
    dx = current_pose.x - target[0]
    dy = current_pose.y - target[1]
    dz = current_pose.z - target[2]
    return sqrt(dx**2 + dy**2 + dz**2) < tolerance

def smooth_move_to_waypoint(waypoint, pose, rate, tolerance=0.3, max_cycles=300, gain=0.2):
    cycle_count = 0
    while not rospy.is_shutdown() and cycle_count < max_cycles:
        if current_pose is None:
            rate.sleep()
            continue
        dx = waypoint[0] - current_pose.x
        dy = waypoint[1] - current_pose.y
        dz = waypoint[2] - current_pose.z
        error = sqrt(dx**2 + dy**2 + dz**2)
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

def execute_trajectory(path_instructions, end_point):
    pose = PoseStamped()
    rate = rospy.Rate(20)  # 20 Hz publication rate
    tolerance = 0.3
    max_cycles = 300
    stabilization_time = 1.0

    rospy.loginfo("Waiting for MAVROS services to be available...")
    rospy.wait_for_service("/mavros/cmd/arming")
    arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
    rospy.wait_for_service("/mavros/set_mode")
    set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

    rospy.loginfo("Waiting for FCU connection...")
    while not rospy.is_shutdown() and not current_state.connected:
        rate.sleep()

    rospy.loginfo("FCU connected, publishing initial setpoints...")
    for _ in range(200):
        local_pos_pub.publish(pose)
        rate.sleep()

    if current_state.mode != "OFFBOARD":
        rospy.loginfo("Setting OFFBOARD mode...")
        try:
            set_mode_response = set_mode_client(base_mode=0, custom_mode="OFFBOARD")
            if set_mode_response.mode_sent:
                rospy.loginfo("OFFBOARD mode enabled.")
            else:
                rospy.logerr("Failed to set OFFBOARD mode.")
        except Exception as e:
            rospy.logerr("Service call failed: %s", e)

    if not current_state.armed:
        rospy.loginfo("Arming the drone...")
        try:
            arming_response = arming_client(value=True)
            if arming_response.success:
                rospy.loginfo("Drone armed.")
            else:
                rospy.logerr("Failed to arm the drone.")
        except Exception as e:
            rospy.logerr("Service call failed: %s", e)

    rospy.loginfo("Starting trajectory execution...")
    for idx, waypoint in enumerate(path_instructions):
        rospy.loginfo("Navigating to waypoint %d: (%.3f, %.3f, %.3f)", idx, waypoint[0], waypoint[1], waypoint[2])
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

# ---------------------------
# Main Execution
# ---------------------------
if __name__ == "__main__":
    rospy.init_node("drone_navigation_node")
    rospy.loginfo("Drone navigation node started.")

    # Define mission parameters
    start_point = (0.0, 1.0, 0.5)
    end_point = (0.0, -6.5, 0.5)
    obstacle_list = [
        (0.0, -1.5, 0.5),
        (0.01, -5.51, 0.5),
        (-2.5, -3.5182, 0.5)
    ]
    
    rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
    main_waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
    rospy.loginfo("Main waypoints received: %s", main_waypoints)
    
    # Ensure the final waypoint exactly matches the end point.
    if main_waypoints:
        main_waypoints[-1] = end_point

    # Generate a smooth, refined path with intermediate waypoints and detours
    refined_path = generate_smooth_path_with_intermediate_waypoints(main_waypoints, obstacle_list, step_size=0.1)
    rospy.loginfo("Final refined path with intermediate waypoints:")
    for idx, point in enumerate(refined_path):
        rospy.loginfo("Waypoint %d: %s", idx, point)
    
    execute_trajectory(refined_path, end_point)
# #


# 
#  #!/usr/bin/env python3
# import rospy
# import time
# import re
# from math import sqrt
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped, Point
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, SetMode

# # Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek R1)
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# # Global state variables
# current_state = State()
# current_pose = None  # Drone's current position

# def state_cb(msg):
#     global current_state
#     current_state = msg

# def pose_cb(msg):
#     global current_pose
#     current_pose = msg.pose.position

# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)
# rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

# def get_llm_navigation_instructions(start, end, obstacles, max_retries=3, delay_between=5.0):
#     """
#     Request navigation instructions from the DeepSeek model via NVIDIA NIM API.
#     """
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         "Your answer must follow these instructions EXACTLY:\n"
#         "1. The path must start at the 'Start' point and end at the 'End' point.\n"
#         "2. The path must avoid all obstacles completely. Do not include any waypoint that is at or too near an obstacle.\n"
#         "3. Do not include any chain-of-thought, reasoning, or additional commentary.\n"
#         "4. Output EXACTLY in the following format with nothing else:\n\n"
#         "BEGIN\n"
#         "(x1, y1, z1)\n"
#         "(x2, y2, z2)\n"
#         "...\n"
#         "(xn, yn, zn)\n"
#         "END\n\n"
#         f"Start: {start}\n"
#         f"End: {end}\n"
#         f"Obstacles: {obstacle_str}\n"
#         "Do not include any extra text."
#     )
#     rospy.loginfo("Sending prompt to DeepSeek model:\n%s", prompt)
    
#     instructions = ""
#     for attempt in range(max_retries):
#         try:
#             # Include a system message to enforce format instructions.
#             completion = client.chat.completions.create(
#                 model="deepseek-ai/deepseek-r1",
#                 messages=[
#                     {"role": "system", "content": "You are a drone path planning assistant. Do not include any chain-of-thought or commentary. Your output must include only the final list of waypoints exactly between the markers 'BEGIN' and 'END'."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=0.0,   # Deterministic output
#                 top_p=1.0,
#                 max_tokens=150,
#                 stream=False
#             )
#             rospy.loginfo("API Response Received (Attempt %d): %s", attempt + 1, completion)
            
#             # Extract the instructions from the API response
#             if hasattr(completion, "choices") and completion.choices:
#                 if hasattr(completion.choices[0], "message"):
#                     instructions = completion.choices[0].message.content
#                 elif hasattr(completion.choices[0], "text"):
#                     instructions = completion.choices[0].text
            
#             if instructions.strip():
#                 break
#             else:
#                 rospy.logwarn("Empty instructions received on attempt %d.", attempt + 1)
#         except Exception as e:
#             rospy.logerr("Error on API call attempt %d: %s", attempt + 1, e)
#             if "429" in str(e):  # Handle rate limits
#                 rospy.logwarn("Rate limit exceeded. Waiting before retrying...")
#                 rospy.sleep(10.0)
#         rospy.sleep(delay_between)
    
#     if not instructions.strip():
#         rospy.logerr("No instructions received from DeepSeek after %d attempts. Using fallback waypoints.", max_retries)
#         return [start, end]
    
#     # Parse the waypoints from the instructions
#     waypoints = parse_waypoints(instructions)
#     rospy.loginfo("Parsed waypoints: %s", waypoints)
    
#     if not waypoints:
#         rospy.logerr("Failed to parse valid waypoints from the API response. Using fallback waypoints.")
#         return [start, end]
    
#     # Optionally filter out any waypoints too close to obstacles.
#     waypoints = filter_obstacle_waypoints(waypoints, obstacles)
    
#     return waypoints

# def parse_waypoints(instructions):
#     """
#     Extract waypoints from the instructions.
#     First, attempt to find text between the markers BEGIN and END.
#     If not found, fall back to extracting all coordinate tuples from the entire response.
#     """
#     begin_marker = "BEGIN"
#     end_marker = "END"
#     start_index = instructions.find(begin_marker)
#     end_index = instructions.find(end_marker, start_index)
#     if start_index != -1 and end_index != -1:
#         relevant_text = instructions[start_index + len(begin_marker):end_index].strip()
#     else:
#         rospy.logwarn("BEGIN/END markers not found. Attempting to extract coordinates from entire response.")
#         relevant_text = instructions
    
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, relevant_text):
#         try:
#             waypoint = tuple(map(float, match.groups()))
#             waypoints.append(waypoint)
#         except ValueError:
#             continue
#     return waypoints

# def filter_obstacle_waypoints(waypoints, obstacles, tolerance=0.2):
#     """
#     Remove any waypoint that is too close to any obstacle.
#     """
#     filtered = []
#     for wp in waypoints:
#         too_close = False
#         for obs in obstacles:
#             distance = sqrt((wp[0]-obs[0])**2 + (wp[1]-obs[1])**2 + (wp[2]-obs[2])**2)
#             if distance < tolerance:
#                 rospy.logwarn("Waypoint %s is too close to obstacle %s. Removing it.", wp, obs)
#                 too_close = True
#                 break
#         if not too_close:
#             filtered.append(wp)
#     return filtered

# def interpolate_waypoints(waypoints, step_distance=0.5):
#     """
#     Generate intermediate waypoints between main waypoints to provide a more detailed path.
#     """
#     detailed = []
#     for i in range(len(waypoints) - 1):
#         start_wp = waypoints[i]
#         end_wp = waypoints[i + 1]
#         # Calculate Euclidean distance between the two waypoints.
#         dist = sqrt((end_wp[0] - start_wp[0])**2 + (end_wp[1] - start_wp[1])**2 + (end_wp[2] - start_wp[2])**2)
#         num_steps = max(int(dist / step_distance), 1)
#         for j in range(num_steps):
#             fraction = j / float(num_steps)
#             inter_wp = (
#                 start_wp[0] + fraction * (end_wp[0] - start_wp[0]),
#                 start_wp[1] + fraction * (end_wp[1] - start_wp[1]),
#                 start_wp[2] + fraction * (end_wp[2] - start_wp[2])
#             )
#             detailed.append(inter_wp)
#     detailed.append(waypoints[-1])
#     return detailed

# def has_reached_waypoint(target, tolerance=0.3):
#     """
#     Check if the drone has reached the target waypoint.
#     """
#     if current_pose is None:
#         return False
#     dx = current_pose.x - target[0]
#     dy = current_pose.y - target[1]
#     dz = current_pose.z - target[2]
#     distance = sqrt(dx**2 + dy**2 + dz**2)
#     return distance < tolerance

# def smooth_move_to_waypoint(waypoint, pose, rate, tolerance=0.3, max_cycles=300, gain=0.2):
#     """
#     Smoothly move the drone to the target waypoint.
#     """
#     cycle_count = 0
#     while not rospy.is_shutdown() and cycle_count < max_cycles:
#         if current_pose is None:
#             rate.sleep()
#             continue
#         dx = waypoint[0] - current_pose.x
#         dy = waypoint[1] - current_pose.y
#         dz = waypoint[2] - current_pose.z
#         error = sqrt(dx**2 + dy**2 + dz**2)
#         if error < tolerance:
#             rospy.loginfo("Reached waypoint: (%.3f, %.3f, %.3f)", waypoint[0], waypoint[1], waypoint[2])
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

# def execute_trajectory(path_instructions, end_point):
#     """
#     Execute the trajectory by moving the drone through the waypoints.
#     """
#     if not path_instructions:
#         rospy.logerr("No path instructions available; aborting trajectory execution.")
#         return

#     pose = PoseStamped()
#     rate = rospy.Rate(20)  # 20 Hz publication rate
#     tolerance = 0.3         # meters
#     max_cycles = 300
#     stabilization_time = 1.0  # seconds

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     # Set OFFBOARD mode
#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         try:
#             set_mode_response = set_mode_client(base_mode=0, custom_mode="OFFBOARD")
#             if set_mode_response.mode_sent:
#                 rospy.loginfo("OFFBOARD mode enabled.")
#             else:
#                 rospy.logerr("Failed to set OFFBOARD mode.")
#         except rospy.ServiceException as e:
#             rospy.logerr("Service call failed: %s", e)

#     # Arm the drone
#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         try:
#             arming_response = arming_client(value=True)
#             if arming_response.success:
#                 rospy.loginfo("Drone armed.")
#             else:
#                 rospy.logerr("Failed to arm the drone.")
#         except rospy.ServiceException as e:
#             rospy.logerr("Service call failed: %s", e)

#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         rospy.loginfo("Moving toward waypoint %d: (%.3f, %.3f, %.3f)", idx, waypoint[0], waypoint[1], waypoint[2])
#         smooth_move_to_waypoint(waypoint, pose, rate, tolerance, max_cycles, gain=0.2)
#         rospy.loginfo("Waypoint %d reached. Stabilizing...", idx)
#         rospy.sleep(stabilization_time)
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

#     # Define start and end points and obstacles
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.03, -1.5, 0.5),
#         (0.07, -5.06, 0.5)
#     ]
    
#     rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
#     main_waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     rospy.loginfo("Main waypoints received: %s", main_waypoints)
    
#     # Ensure the final waypoint exactly matches the end point.
#     if main_waypoints:
#         main_waypoints[-1] = end_point

#     # Generate a detailed path by interpolating intermediate waypoints.
#     detailed_waypoints = interpolate_waypoints(main_waypoints, step_distance=0.5)
#     rospy.loginfo("Detailed waypoints: %s", detailed_waypoints)

#     execute_trajectory(detailed_waypoints, end_point)





# #!/usr/bin/env python3
# import rospy
# import time
# import re
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped, Point
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, SetMode

# # Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek R1)
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# # Global state variables
# current_state = State()
# current_pose = None  # Drone's current position

# def state_cb(msg):
#     global current_state
#     current_state = msg

# def pose_cb(msg):
#     global current_pose
#     current_pose = msg.pose.position

# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)
# rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

# def get_llm_navigation_instructions(start, end, obstacles, max_retries=3, delay_between=5.0):
#     """
#     Request navigation instructions from the DeepSeek model via NVIDIA NIM API.
#     """
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         "Your answer must follow these instructions EXACTLY:\n"
#         "1. The path must start at the 'Start' point and end at the 'End' point.\n"
#         "2. The path must avoid all obstacles completely. Do not include any waypoint that is at or too near an obstacle.\n"
#         "3. Do not include any chain-of-thought, reasoning, or additional commentary.\n"
#         "4. Output EXACTLY in the following format with nothing else:\n\n"
#         "BEGIN\n"
#         "(x1, y1, z1)\n"
#         "(x2, y2, z2)\n"
#         "...\n"
#         "(xn, yn, zn)\n"
#         "END\n\n"
#         f"Start: {start}\n"
#         f"End: {end}\n"
#         f"Obstacles: {obstacle_str}\n"
#         "Do not include any extra text."
#     )
#     rospy.loginfo("Sending prompt to DeepSeek model:\n%s", prompt)
    
#     instructions = ""
#     for attempt in range(max_retries):
#         try:
#             # Include a system message to enforce format instructions
#             completion = client.chat.completions.create(
#                 model="deepseek-ai/deepseek-r1",
#                 messages=[
#                     {"role": "system", "content": "You are a drone path planning assistant. Do not include any chain-of-thought or commentary. Your output must include only the final list of waypoints exactly between the markers 'BEGIN' and 'END'."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=0.0,   # Deterministic output
#                 top_p=1.0,
#                 max_tokens=150,    # Lowering token count may help keep the output short
#                 stream=False
#             )
#             rospy.loginfo("API Response Received (Attempt %d): %s", attempt + 1, completion)
            
#             # Extract the instructions from the API response
#             if hasattr(completion, "choices") and completion.choices:
#                 if hasattr(completion.choices[0], "message"):
#                     instructions = completion.choices[0].message.content
#                 elif hasattr(completion.choices[0], "text"):
#                     instructions = completion.choices[0].text
            
#             if instructions.strip():
#                 break
#             else:
#                 rospy.logwarn("Empty instructions received on attempt %d.", attempt + 1)
#         except Exception as e:
#             rospy.logerr("Error on API call attempt %d: %s", attempt + 1, e)
#             if "429" in str(e):  # Handle rate limits
#                 rospy.logwarn("Rate limit exceeded. Waiting before retrying...")
#                 rospy.sleep(10.0)  # Wait longer before retrying
#         rospy.sleep(delay_between)
    
#     if not instructions.strip():
#         rospy.logerr("No instructions received from DeepSeek after %d attempts. Using fallback waypoints.", max_retries)
#         # Fallback waypoints (straight line from start to end)
#         return [start, end]
    
#     # Parse the waypoints from the instructions
#     waypoints = parse_waypoints(instructions)
#     rospy.loginfo("Parsed waypoints: %s", waypoints)
    
#     if not waypoints:
#         rospy.logerr("Failed to parse valid waypoints from the API response. Using fallback waypoints.")
#         return [start, end]  # Fallback to a straight line
    
#     # Optionally filter out any waypoints too close to obstacles
#     waypoints = filter_obstacle_waypoints(waypoints, obstacles)
    
#     return waypoints

# def parse_waypoints(instructions):
#     """
#     Extract waypoints from the instructions.
#     First, attempt to find text between the markers BEGIN and END.
#     If not found, fall back to extracting all coordinate tuples from the entire response.
#     """
#     begin_marker = "BEGIN"
#     end_marker = "END"
#     start_index = instructions.find(begin_marker)
#     end_index = instructions.find(end_marker, start_index)
#     if start_index != -1 and end_index != -1:
#         relevant_text = instructions[start_index + len(begin_marker):end_index].strip()
#     else:
#         rospy.logwarn("BEGIN/END markers not found. Attempting to extract coordinates from entire response.")
#         relevant_text = instructions
    
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, relevant_text):
#         try:
#             waypoint = tuple(map(float, match.groups()))
#             waypoints.append(waypoint)
#         except ValueError:
#             continue
#     return waypoints

# def filter_obstacle_waypoints(waypoints, obstacles, tolerance=0.2):
#     """
#     Remove any waypoint that is too close to any obstacle.
#     """
#     filtered = []
#     for wp in waypoints:
#         too_close = False
#         for obs in obstacles:
#             distance = ((wp[0]-obs[0])**2 + (wp[1]-obs[1])**2 + (wp[2]-obs[2])**2)**0.5
#             if distance < tolerance:
#                 rospy.logwarn("Waypoint %s is too close to obstacle %s. Removing it.", wp, obs)
#                 too_close = True
#                 break
#         if not too_close:
#             filtered.append(wp)
#     return filtered

# def has_reached_waypoint(target, tolerance=0.3):
#     """
#     Check if the drone has reached the target waypoint.
#     """
#     if current_pose is None:
#         return False
#     dx = current_pose.x - target[0]
#     dy = current_pose.y - target[1]
#     dz = current_pose.z - target[2]
#     distance = (dx**2 + dy**2 + dz**2)**0.5
#     return distance < tolerance

# def smooth_move_to_waypoint(waypoint, pose, rate, tolerance=0.3, max_cycles=300, gain=0.2):
#     """
#     Smoothly move the drone to the target waypoint.
#     """
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
#             rospy.loginfo("Reached waypoint: (%.3f, %.3f, %.3f)", waypoint[0], waypoint[1], waypoint[2])
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

# def execute_trajectory(path_instructions, end_point):
#     """
#     Execute the trajectory by moving the drone through the waypoints.
#     """
#     if not path_instructions:
#         rospy.logerr("No path instructions available; aborting trajectory execution.")
#         return

#     pose = PoseStamped()
#     rate = rospy.Rate(20)  # 20 Hz publication rate
#     tolerance = 0.3         # meters
#     max_cycles = 300
#     stabilization_time = 1.0  # seconds

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     # Set OFFBOARD mode
#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         try:
#             set_mode_response = set_mode_client(base_mode=0, custom_mode="OFFBOARD")
#             if set_mode_response.mode_sent:
#                 rospy.loginfo("OFFBOARD mode enabled.")
#             else:
#                 rospy.logerr("Failed to set OFFBOARD mode.")
#         except rospy.ServiceException as e:
#             rospy.logerr("Service call failed: %s", e)

#     # Arm the drone
#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         try:
#             arming_response = arming_client(value=True)
#             if arming_response.success:
#                 rospy.loginfo("Drone armed.")
#             else:
#                 rospy.logerr("Failed to arm the drone.")
#         except rospy.ServiceException as e:
#             rospy.logerr("Service call failed: %s", e)

#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         rospy.loginfo("Moving toward waypoint %d: (%.3f, %.3f, %.3f)", idx, waypoint[0], waypoint[1], waypoint[2])
#         smooth_move_to_waypoint(waypoint, pose, rate, tolerance, max_cycles, gain=0.2)
#         rospy.loginfo("Waypoint %d reached. Stabilizing...", idx)
#         rospy.sleep(stabilization_time)
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

#     # Define start and end points and obstacles
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.03, -1.5, 0.5),
#         (0.07, -5.06, 0.5)
#     ]
    
#     rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
#     waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     rospy.loginfo("Waypoints received: %s", waypoints)
#     if waypoints:
#         # Ensure the final waypoint exactly matches the end point
#         waypoints[-1] = end_point
#         execute_trajectory(waypoints, end_point)
#     else:
#         rospy.logerr("No valid waypoints received from DeepSeek; aborting mission.")


# #!/usr/bin/env python3
# import rospy
# import time
# import re
# from openai import OpenAI
# from geometry_msgs.msg import PoseStamped, Point
# from mavros_msgs.msg import State
# from mavros_msgs.srv import CommandBool, SetMode

# # Initialize the OpenAI API client with NVIDIA NIM endpoint (DeepSeek R1)
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )

# # Global state variables
# current_state = State()
# current_pose = None  # Drone's current position

# def state_cb(msg):
#     global current_state
#     current_state = msg

# def pose_cb(msg):
#     global current_pose
#     current_pose = msg.pose.position

# local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)
# rospy.Subscriber("mavros/state", State, state_cb)
# rospy.Subscriber("mavros/local_position/pose", PoseStamped, pose_cb)

# def get_llm_navigation_instructions(start, end, obstacles, max_retries=3, delay_between=5.0):
#     """
#     Request navigation instructions from the DeepSeek model via NVIDIA NIM API.
#     """
#     # Prepare obstacle string and the prompt
#     obstacle_str = "; ".join(f"{obs}" for obs in obstacles)
#     prompt = (
#         "You are a drone path planning assistant. Provide ONLY the final list of main waypoints for a smooth path "
#         "from start to end. The path must begin at the start and end at the end, and progress smoothly without backtracking. "
#         "Output the answer EXACTLY in the following format (each waypoint on a new line):\n\n"
#         "BEGIN\n"
#         "(x1, y1, z1)\n"
#         "(x2, y2, z2)\n"
#         "...\n"
#         "(xn, yn, zn)\n"
#         "END\n\n"
#         f"Start: {start}\n"
#         f"End: {end}\n"
#         f"Obstacles: {obstacle_str}\n"
#         "Do not include any additional commentary or chain-of-thought in your output."
#     )
#     rospy.loginfo("Sending prompt to DeepSeek model:\n%s", prompt)
    
#     instructions = ""
#     for attempt in range(max_retries):
#         try:
#             # Make the API call without a timeout
#             completion = client.chat.completions.create(
#                 model="deepseek-ai/deepseek-r1",
#                 messages=[{"role": "user", "content": prompt}],
#                 temperature=0.0,   # Deterministic output
#                 top_p=1.0,
#                 max_tokens=256,
#                 stream=False
#             )
#             rospy.loginfo("API Response Received (Attempt %d): %s", attempt + 1, completion)
            
#             # Extract the instructions from the API response
#             if hasattr(completion, "choices") and completion.choices:
#                 if hasattr(completion.choices[0], "message"):
#                     instructions = completion.choices[0].message.content
#                 elif hasattr(completion.choices[0], "text"):
#                     instructions = completion.choices[0].text
            
#             if instructions.strip():
#                 break
#             else:
#                 rospy.logwarn("Empty instructions received on attempt %d.", attempt + 1)
#         except Exception as e:
#             rospy.logerr("Error on API call attempt %d: %s", attempt + 1, e)
#             if "429" in str(e):  # Handle rate limits
#                 rospy.logwarn("Rate limit exceeded. Waiting before retrying...")
#                 rospy.sleep(10.0)  # Wait longer before retrying
#         rospy.sleep(delay_between)
    
#     if not instructions.strip():
#         rospy.logerr("No instructions received from DeepSeek after %d attempts. Using fallback waypoints.", max_retries)
#         # Fallback waypoints (straight line from start to end)
#         return [start, end]
    
#     # Parse the waypoints from the instructions
#     waypoints = parse_waypoints(instructions)
#     rospy.loginfo("Parsed waypoints: %s", waypoints)
    
#     if not waypoints:
#         rospy.logerr("Failed to parse valid waypoints from the API response. Using fallback waypoints.")
#         return [start, end]  # Fallback to a straight line
    
#     return waypoints

# def parse_waypoints(instructions):
#     """
#     Extract waypoints from the instructions.
#     """
#     waypoints = []
#     pattern = r"\(([\d\.-]+),\s*([\d\.-]+),\s*([\d\.-]+)\)"
#     for match in re.finditer(pattern, instructions):
#         try:
#             waypoint = tuple(map(float, match.groups()))
#             waypoints.append(waypoint)
#         except ValueError:
#             continue
#     return waypoints

# def has_reached_waypoint(target, tolerance=0.3):
#     """
#     Check if the drone has reached the target waypoint.
#     """
#     if current_pose is None:
#         return False
#     dx = current_pose.x - target[0]
#     dy = current_pose.y - target[1]
#     dz = current_pose.z - target[2]
#     distance = (dx**2 + dy**2 + dz**2)**0.5
#     return distance < tolerance

# def smooth_move_to_waypoint(waypoint, pose, rate, tolerance=0.3, max_cycles=300, gain=0.2):
#     """
#     Smoothly move the drone to the target waypoint.
#     """
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
#             rospy.loginfo("Reached waypoint: (%.3f, %.3f, %.3f)", waypoint[0], waypoint[1], waypoint[2])
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

# def execute_trajectory(path_instructions, end_point):
#     """
#     Execute the trajectory by moving the drone through the waypoints.
#     """
#     if not path_instructions:
#         rospy.logerr("No path instructions available; aborting trajectory execution.")
#         return

#     pose = PoseStamped()
#     rate = rospy.Rate(20)  # 20 Hz publication rate
#     tolerance = 0.3         # meters
#     max_cycles = 300
#     stabilization_time = 1.0  # seconds

#     rospy.loginfo("Waiting for MAVROS services to be available...")
#     rospy.wait_for_service("/mavros/cmd/arming")
#     arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
#     rospy.wait_for_service("/mavros/set_mode")
#     set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

#     rospy.loginfo("Waiting for FCU connection...")
#     while not rospy.is_shutdown() and not current_state.connected:
#         rate.sleep()

#     rospy.loginfo("FCU connected, publishing initial setpoints...")
#     for _ in range(200):
#         local_pos_pub.publish(pose)
#         rate.sleep()

#     # Set OFFBOARD mode
#     if current_state.mode != "OFFBOARD":
#         rospy.loginfo("Setting OFFBOARD mode...")
#         try:
#             set_mode_response = set_mode_client(base_mode=0, custom_mode="OFFBOARD")
#             if set_mode_response.mode_sent:
#                 rospy.loginfo("OFFBOARD mode enabled.")
#             else:
#                 rospy.logerr("Failed to set OFFBOARD mode.")
#         except rospy.ServiceException as e:
#             rospy.logerr("Service call failed: %s", e)

#     # Arm the drone
#     if not current_state.armed:
#         rospy.loginfo("Arming the drone...")
#         try:
#             arming_response = arming_client(value=True)
#             if arming_response.success:
#                 rospy.loginfo("Drone armed.")
#             else:
#                 rospy.logerr("Failed to arm the drone.")
#         except rospy.ServiceException as e:
#             rospy.logerr("Service call failed: %s", e)

#     rospy.loginfo("Starting trajectory execution...")
#     for idx, waypoint in enumerate(path_instructions):
#         rospy.loginfo("Moving toward waypoint %d: (%.3f, %.3f, %.3f)", idx, waypoint[0], waypoint[1], waypoint[2])
#         smooth_move_to_waypoint(waypoint, pose, rate, tolerance, max_cycles, gain=0.2)
#         rospy.loginfo("Waypoint %d reached. Stabilizing...", idx)
#         rospy.sleep(stabilization_time)
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

#     # Define start and end points and obstacles
#     start_point = (0.0, 1.0, 0.5)
#     end_point = (0.0, -6.5, 0.5)
#     obstacle_list = [
#         (0.03, -1.5, 0.5),
#         (0.07, -5.06, 0.5)
#     ]
    
#     rospy.loginfo("Requesting navigation instructions from DeepSeek model...")
#     waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
#     rospy.loginfo("Waypoints received: %s", waypoints)
#     if waypoints:
#         # Ensure the final waypoint exactly matches the end point
#         waypoints[-1] = end_point
#         execute_trajectory(waypoints, end_point)
#     else:
#         rospy.logerr("No valid waypoints received from DeepSeek; aborting mission.")