import random
import math
from pathlib import Path

def format_with_underscores(value):
    """Formats an integer with underscores every three digits."""
    return f"{value:_}"

def generate_lattice_toml(width_count, height_count, sep_x, sep_y, start_x=120, start_y=120):
    output_lines = []
    
    for row in range(height_count):
        for col in range(width_count):
            bot_id = row * width_count + col + 1
            address = f"AAAAAAAA{bot_id:08X}"
            
            # Calculate positions
            pos_x = start_x + (col * sep_x)
            pos_y = start_y + (row * sep_y)
            
            # Randomize theta between 0 and 2*pi
            random_theta = round(random.uniform(0, 2 * math.pi), 2)

            # Manually build the TOML entry string to preserve underscores
            output_lines.append("[[dotbots]]")
            output_lines.append(f'address = "{address}"')
            output_lines.append(f'pos_x = {pos_x:_}')
            output_lines.append(f'pos_y = {pos_y:_}')
            output_lines.append(f"theta = {random_theta}")
            output_lines.append("") # Empty line for readability
            
    return "\n".join(output_lines)

# --- Configuration ---
WIDTH_NODES = 5  # Robots per row
HEIGHT_NODES = 5 # Number of rows
SEP_X = 240  # Separation between columns
SEP_Y = 240  # Separation between rows

# Generate
toml_string = generate_lattice_toml(WIDTH_NODES, HEIGHT_NODES, SEP_X, SEP_Y)

# Save to file
output_path = Path(__file__).resolve().parent / "init_state.toml"
with open(output_path, "w") as f:
    f.write(toml_string)

print(f"Generated TOML file at {output_path}")