import math
import random
import numpy as np
import re
import datetime

def convert_numpy_coords(obj):
    """
    Recursively convert numpy data types to native Python types for JSON serialization.
    """
    if isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.complexfloating,)):
        return complex(obj)
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (list, tuple)):
        converted = [convert_numpy_coords(item) for item in obj]
        return tuple(converted) if isinstance(obj, tuple) else converted
    elif isinstance(obj, dict):
        return {key: convert_numpy_coords(value) for key, value in obj.items()}
    return obj  # Unchanged types

def log_batch_of_data(agent_histories, add_log, prefix="batch"):
    """
    Log a batch of data from all agents. One log per agent per data point.
    Parameters:
    agent_histories (dict): Mapping of agent_id to list of data points
    add_log (function): Function to add logs to the RAG store
    prefix (str): Prefix used to construct a unique log ID
    """
    print(f"[LOGGING] Logging batch of data with prefix: {prefix}")
    for agent_id, history in agent_histories.items():
        prev_entry = None
        for i, data in enumerate(history):
            if data == prev_entry:
                continue
            prev_entry = data
            
            # Create the data without creating a separate log_id
            position = convert_numpy_coords(data['position'])
            comm_quality = convert_numpy_coords(data['communication_quality'])
            jammed = data['jammed']
            timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
            
            log_text = (
                f"Agent {agent_id} is at position {position}. "
                f"Communication quality: {comm_quality}. "
                f"Status: {'Jammed' if jammed else 'Clear'}."
            )
            
            metadata = {
                'timestamp': timestamp,
                'agent_id': agent_id,
                'comm_quality': comm_quality,
                'position': position,
                'jammed': jammed,
                'role': 'system',
                'source': 'simulation',
                'batch_index': i,  # Keep track of the sequence if needed
                'batch_prefix': prefix
            }
            
            # Simply call add_log with the text and metadata
            add_log(log_text=log_text, metadata=metadata)
            
def round_coord(value):
    """Round coordinates to 3 decimal places"""
    return round(value, 3)

def is_jammed(pos, jamming_center, jamming_radius):
    """Check if a position is inside the jamming zone"""
    if isinstance(pos, tuple) or isinstance(pos, list):
        pos_x, pos_y = pos[0], pos[1]
    else:  # Assume numpy array
        pos_x, pos_y = pos[0], pos[1]
    
    distance = math.sqrt((pos_x - jamming_center[0])**2 + (pos_y - jamming_center[1])**2)
    return distance <= jamming_radius

def linear_path(start, end, max_movement_per_step):
    """Create a linear path between start and end points with max step distance constraint"""
    step_size = max_movement_per_step
    path = []
    
    # Convert to numpy arrays if they aren't already
    if isinstance(start, tuple) or isinstance(start, list):
        start_np = np.array([start[0], start[1]])
    else:
        start_np = start
        
    if isinstance(end, tuple) or isinstance(end, list):
        end_np = np.array([end[0], end[1]])
    else:
        end_np = end
    
    direction_x, direction_y = end_np[0] - start_np[0], end_np[1] - start_np[1]
    distance = math.sqrt(direction_x**2 + direction_y**2)
    
    if distance > 0:
        unit_x, unit_y = direction_x / distance, direction_y / distance
    else:
        return [(round_coord(end_np[0]), round_coord(end_np[1]))]
    
    current_x, current_y = start_np[0], start_np[1]
    while math.sqrt((current_x - end_np[0])**2 + (current_y - end_np[1])**2) > step_size:
        current_x += step_size * unit_x
        current_y += step_size * unit_y
        path.append((round_coord(current_x), round_coord(current_y)))
    
    path.append((round_coord(end_np[0]), round_coord(end_np[1])))
    return path

def limit_movement(current_pos, target_pos, max_movement_per_step):
    """Limit movement to max_movement_per_step"""
    if isinstance(current_pos, tuple) or isinstance(current_pos, list):
        current_np = np.array([current_pos[0], current_pos[1]])
    else:
        current_np = current_pos
        
    if isinstance(target_pos, tuple) or isinstance(target_pos, list):
        target_np = np.array([target_pos[0], target_pos[1]])
    else:
        target_np = target_pos
    
    distance = np.linalg.norm(target_np - current_np)
    
    if distance <= max_movement_per_step:
        return target_np  # We can reach the target directly
    
    # Otherwise, move in the direction of the target, but only by max_movement_per_step
    direction = (target_np - current_np) / distance
    limited_pos = current_np + direction * max_movement_per_step
    
    return (round_coord(limited_pos[0]), round_coord(limited_pos[1]))

def algorithm_make_move(agent_id, current_pos, jamming_center, jamming_radius, 
                       max_movement_per_step, x_range, y_range):
    """Use the fittest path algorithm for jammed agents"""
    print(f"[Algorithm] Finding path for Agent {agent_id} at {current_pos}")
    
    # Try to find a valid move that's outside the jamming zone
    max_attempts = 10
    for _ in range(max_attempts):
        # Generate a random direction (unit vector)
        angle = random.uniform(0, 2 * np.pi)
        direction = np.array([np.cos(angle), np.sin(angle)])
        
        # Move max_movement_per_step in that direction
        suggestion = np.array(current_pos) + direction * max_movement_per_step
        
        # Clamp to the boundaries of the plane
        suggestion[0] = max(min(suggestion[0], x_range[1]), x_range[0])
        suggestion[1] = max(min(suggestion[1], y_range[1]), y_range[0])
        
        # Check if this would be outside the jamming zone
        if not is_jammed(suggestion, jamming_center, jamming_radius):
            print(f"[Algorithm] Found non-jammed position for Agent {agent_id}: {suggestion}")
            return (round_coord(suggestion[0]), round_coord(suggestion[1]))
    
    # If we failed to find a good move after max_attempts, try to move away from center
    print(f"[Algorithm] Couldn't find non-jammed position, moving away from jamming center")
    
    # Direction away from jamming center
    direction = np.array(current_pos) - np.array(jamming_center)
    direction_norm = np.linalg.norm(direction)
    
    if direction_norm > 0:
        unit_direction = direction / direction_norm
        suggestion = np.array(current_pos) + unit_direction * max_movement_per_step
    else:
        # If at center, move in random direction
        angle = random.uniform(0, 2 * np.pi)
        unit_direction = np.array([np.cos(angle), np.sin(angle)])
        suggestion = np.array(current_pos) + unit_direction * max_movement_per_step
    
    # Clamp to the boundaries
    suggestion[0] = max(min(suggestion[0], x_range[1]), x_range[0])
    suggestion[1] = max(min(suggestion[1], y_range[1]), y_range[0])
    
    return (round_coord(suggestion[0]), round_coord(suggestion[1]))

def llm_make_move(agent_id, swarm_pos_dict, num_history_segments, ollama, LLM_MODEL, MAX_CHARS_PER_AGENT, 
                 MAX_RETRIES, jamming_center, jamming_radius, max_movement_per_step, x_range, y_range):
    """Use LLM to determine movement for jammed agents"""
    # Get the last positions for the agent
    last_positions = swarm_pos_dict[agent_id][-num_history_segments:]
    last_valid_position = last_positions[-1][:2]  # Get the last recorded position
    
    # Prepare a movement history string for the last positions
    position_history_str = "\n".join([f"({pos[0]}, {pos[1]})" for pos in last_positions])
    
    print(f"Prompting LLM for new coordinate for {agent_id} from {last_valid_position}")
    
    # Create the prompt message with the position history
    prompt = f"Agent {agent_id} is jammed at {last_valid_position}. " \
             f"Here are the last {num_history_segments} positions:\n{position_history_str}\n" \
             f"Provide exactly one new coordinate pair as (x, y) with both values being numbers. " \
             f"Your response must be 25 characters or less and should only contain the coordinate. "
    
    print(f"Full prompt sent to LLM: {prompt}")
    
    # Try multiple times to get a valid response
    for attempt in range(MAX_RETRIES):
        try:
            # Send the prompt with a timeout
            response = ollama.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Get and print the full response
            response_content = response.get('message', {}).get('content', '')
            print(f"Full LLM response: \"{response_content}\"")
            
            # Check if response exceeds character limit
            if len(response_content) > MAX_CHARS_PER_AGENT:
                print(f"Response exceeds character limit ({len(response_content)} > {MAX_CHARS_PER_AGENT}), retrying...")
                continue
            
            # Parse the response for the new coordinate
            new_coordinate = parse_llm_response(response_content)
            
            if new_coordinate:
                print(f"LLM provided new coordinate for {agent_id}: {new_coordinate}")
                return new_coordinate
            else:
                print(f"Failed to parse coordinates, retrying (attempt {attempt+1}/{MAX_RETRIES})...")
        
        except Exception as e:
            print(f"Error getting LLM response: {e}. Retrying (attempt {attempt+1}/{MAX_RETRIES})...")
    
    # If we get here, we didn't get a valid response after all retries
    print(f"Failed to get valid coordinates after {MAX_RETRIES} attempts. Using algorithm instead.")
    
    # Fall back to algorithm if LLM fails
    return algorithm_make_move(agent_id, last_valid_position, jamming_center, jamming_radius, 
                              max_movement_per_step, x_range, y_range)

def get_last_safe_position(agent_id, last_safe_position, swarm_pos_dict, high_comm_qual):
    """
    Retrieves the last known safe position for an agent, 
    defined as the most recent position with high communication quality.
    """
    if agent_id in last_safe_position:
        safe_pos = last_safe_position[agent_id]
        print(f"Agent {agent_id}: Returning to stored safe position {safe_pos}")
        return safe_pos

    # If no stored safe position, find one from history
    for pos in reversed(swarm_pos_dict[agent_id]):
        if pos[2] >= high_comm_qual:  # Communication quality must be high
            print(f"Agent {agent_id}: Found historical safe position {pos[:2]}")
            return pos[:2]  # Return the coordinates
            
    # If no valid position found, return the current position
    current_pos = swarm_pos_dict[agent_id][-1][:2]
    print(f"Agent {agent_id}: No valid safe position found, using current position {current_pos}")
    return current_pos