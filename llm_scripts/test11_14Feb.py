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
        "Plan a path that detours smoothly around these obstacles, with each waypoint moving closer to the endpoint, avoiding backtracking, and following a smooth trajectory."
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

# Check if the new point is closer to the endpoint than the previous point to prevent backtracking
def is_closer_to_endpoint(new_point, last_point, endpoint):
    new_dist = sum((new_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
    last_dist = sum((last_point[i] - endpoint[i]) ** 2 for i in range(3)) ** 0.5
    return new_dist < last_dist

# Generate a smooth path that strictly progresses towards the endpoint, avoiding obstacles
def generate_smooth_path_with_intermediate_waypoints(waypoints, obstacles, step_size=0.1):
    refined_path = []
    last_point = waypoints[0]

    for waypoint in waypoints:
        distance = sum((waypoint[i] - last_point[i]) ** 2 for i in range(3)) ** 0.5
        direction = [(waypoint[i] - last_point[i]) / distance for i in range(3)] if distance > 0 else [0, 0, 0]

        num_intermediate_steps = int(distance // step_size)
        for step in range(1, num_intermediate_steps + 1):
            intermediate_waypoint = tuple(
                last_point[i] + direction[i] * step * step_size for i in range(3)
            )
            if is_closer_to_endpoint(intermediate_waypoint, last_point, waypoints[-1]):
                refined_path.append(intermediate_waypoint)
        
        if is_closer_to_endpoint(waypoint, last_point, waypoints[-1]):
            refined_path.append(waypoint)
        
        last_point = waypoint

    refined_path = avoid_obstacles(refined_path, obstacles, step_size)
    return refined_path

# Refined obstacle avoidance to ensure forward-only progression
def avoid_obstacles(path, obstacles, step_size):
    safe_path = []
    obstacle_clearance = 1.1
    for idx, point in enumerate(path):
        safe = True
        for obs_x, obs_y, obs_z in obstacles:
            if (obs_x - 1 <= point[0] <= obs_x + 1 and
                obs_y - 1 <= point[1] <= obs_y + 1 and
                obs_z - 1 <= point[2] <= obs_z + 1):
                safe = False
                break

        if safe:
            safe_path.append(point)
        else:
            detour_waypoints = create_detour(point, path[idx + 1] if idx + 1 < len(path) else path[-1], obstacles)
            safe_path.extend(detour_waypoints)

    return safe_path

# Refined detour to prevent backtracking
def create_detour(start, end, obstacles, clearance=1.1):
    detour_path = []
    for obs in obstacles:
        sx, sy, sz = start
        ex, ey, ez = end
        ox, oy, oz = obs
        
        if abs(ex - ox) > abs(ey - oy):
            if sy < oy:
                detour_path.append((sx, oy - clearance, sz))
            else:
                detour_path.append((sx, oy + clearance, sz))
            detour_path.append((ex, detour_path[-1][1], ez))
        else:
            if sx < ox:
                detour_path.append((ox - clearance, sy, sz))
            else:
                detour_path.append((ox + clearance, sy, sz))
            detour_path.append((detour_path[-1][0], ey, ez))

    return detour_path

# Execute the trajectory and hold the final waypoint
def execute_trajectory(path_instructions, end_point):
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

    while not rospy.is_shutdown() and not current_state.connected:
        rate.sleep()

    for _ in range(200):
        local_pos_pub.publish(pose)
        rate.sleep()

    if current_state.mode != "OFFBOARD":
        set_mode_client.call(offb_set_mode)
    if not current_state.armed:
        arming_client.call(arm_cmd)

    # Execute and log each waypoint
    for idx, waypoint in enumerate(path_instructions):
        x, y, z = waypoint
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = z

        rospy.loginfo("Navigating to waypoint %d: (%.3f, %.3f, %.3f)", idx, x, y, z)
        for _ in range(10):
            local_pos_pub.publish(pose)
            rate.sleep()

        if waypoint == end_point:
            break

    # Hold the final position
    while not rospy.is_shutdown():
        pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = end_point
        local_pos_pub.publish(pose)
        rate.sleep()

# Main function
if __name__ == "__main__":
    rospy.init_node("drone_navigation_node")
    start_point = (0.0, 1, 0.5)
    end_point = (-2.5, -6.5, 0.5)
    
    obstacle_list = [
        (0.0, -1.5, 0.5), (0.01, -5.51, 0.5), (-2.5, -3.518200,0.5)
    ]
    waypoints = get_llm_navigation_instructions(start_point, end_point, obstacle_list)
    if waypoints:
        waypoints[-1] = end_point
        refined_path = generate_smooth_path_with_intermediate_waypoints(waypoints, obstacle_list)
        
        # Log every intermediate point in the path
        rospy.loginfo("Final refined path with intermediate waypoints:")
        for idx, point in enumerate(refined_path):
            rospy.loginfo("Waypoint %d: %s", idx, point)
        
        execute_trajectory(refined_path, end_point)
    else:
        rospy.logerr("No path found to the destination.")
