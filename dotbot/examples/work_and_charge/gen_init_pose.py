from pathlib import Path

def generate_dotbot_script():
    # Configuration Constants
    NUM_ROBOTS = 8       # Total robots to generate
    START_ID = 1         # Start at AAAAAAAA00000001
    X_RIGHT = 800
    X_LEFT = 100
    START_Y = 200
    Y_STEP = 200
    THETA = 3.14
    FILENAME = "dotbots_config.toml"

    lines = []

    for i in range(NUM_ROBOTS):
        # 1. Address: Increments by 1 every robot
        address_hex = f"AAAAAAAA{START_ID + i:08X}"

        # 2. X Position: Alternates 800, 100, 800, 100...
        pos_x_val = X_RIGHT if i % 2 == 0 else X_LEFT

        # 3. Y Position: Increases by 200 for EVERY robot
        pos_y_val = START_Y + (i * Y_STEP)

        # 4. Format numbers with underscores (e.g., 800_000)
        pos_x = f"{pos_x_val:,}".replace(",", "_")
        pos_y = f"{pos_y_val:,}".replace(",", "_")

        # Build the TOML block
        block = (
            f"[[dotbots]]\n"
            f"address = \"{address_hex}\"\n"
            f"pos_x = {pos_x}\n"
            f"pos_y = {pos_y}\n"
            f"theta = {THETA}\n"
        )
        lines.append(block)

    # Save to file
    output_path = Path(__file__).resolve().parent / "init_state.toml"
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Generated TOML file at {output_path}")
    
if __name__ == "__main__":
    generate_dotbot_script()