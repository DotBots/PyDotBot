import keyboard  
import dotbot_cmd

def onkeypress(event):
    # print(event.name)

    if event.name == "enter":
        dotbot_cmd.command_move(0, 0) 
    elif event.name == "left":
        dotbot_cmd.command_move(0, 1) 
    elif event.name == "right":
        dotbot_cmd.command_move(0, -1) 
    elif event.name == "up":
        dotbot_cmd.command_move(1, 0) 
    elif event.name == "down":
        dotbot_cmd.command_move(-1, 0) 

keyboard.on_press(onkeypress)

#Use ctrl+c to stop
while True:
    pass