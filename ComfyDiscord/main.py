import discord
from discord import app_commands
from discord.ext import tasks
import typing
import websocket #NOTE: websocket-client (https://github.com/websocket-client/websocket-client)
import uuid
import json
import urllib.request
import urllib.parse
import random
import asyncio
import os
import sys

from request import call
from models import models_config
from key import key

global bad_prompt_words
bad_prompt_words = "text, watermark"

global cur_model
cur_model = "Yiffymix"

# List of user IDs that are authorized to use the generate command
AUTHORIZED_BOT_USERS = [951510569700171867, 770518291273089026, 521365728767508480]

# List of user IDs that are authorized to use the kill command
AUTHORIZED_KILL_USERS = [951510569700171867]

# List of user IDs that are authorized to use the restart command
AUTHORIZED_RESTART_USERS = [951510569700171867, 770518291273089026]

class aclient(discord.AutoShardedClient):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents, activity=discord.CustomActivity(name="Generating [redacted]", emoji="🐺", status = discord.Status.online))
    async def on_ready(self):
        await tree.sync()
        print("Starting image generation bot as {0.user}".format(bot))

bot = aclient()
tree = app_commands.CommandTree(bot)

async def generate(interaction, prompt, model, negative):
    global cur_model
    if model == cur_model:
        await interaction.response.send_message("Please wait for your image to be generated :3")
    else:
        await interaction.response.send_message("Please wait for your image to be generated :3 | Model swap, delay expected")
        cur_model = model
    server_address = "127.0.0.1:8188"
    client_id = str(uuid.uuid4())

    async def queue_prompt(prompta):
        p = {"prompt": prompta, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')
        
        req = await asyncio.get_event_loop().run_in_executor(
            None, lambda: urllib.request.Request("http://{}/prompt".format(server_address), data=data)
        ) 
        print(req)
        return json.loads(urllib.request.urlopen(req).read())

    def get_image(filename, subfolder, folder_type):
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = urllib.parse.urlencode(data)
        with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
            return response.read()

    def get_history(prompt_id):
        with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
            return json.loads(response.read())

    async def get_images(ws, prompta):
        prompt_id = await queue_prompt(prompta)
        prompt_id = prompt_id['prompt_id']
        print(prompt_id)
        output_images = {}
        current_node = ""
        while True:
            out = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ws.recv()
            )
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing':
                    data = message['data']
                    if data['prompt_id'] == prompt_id:
                        if data['node'] is None:
                            break #Execution is done
                        else:
                            current_node = data['node']
            else:
                if current_node == 'save_image_websocket_node':
                    images_output = output_images.get(current_node, [])
                    images_output.append(out[8:])
                    output_images[current_node] = images_output

        return output_images

    prompta = json.loads(call)
    #set the text prompt for our positive CLIPTextEncode
    prompta["18"]["inputs"]["text"] = prompt
    prompta["19"]["inputs"]["text"] = bad_prompt_words + negative
    prompta["17"]["inputs"]["seed"] = random.randint(0, 10000000000000)
    prompta["16"]["inputs"]["ckpt_name"] = models_config["models"][model]["filename"]
    prompta["17"]["inputs"]["scheduler"] = models_config["models"][model]["scheduler"]
    prompta["17"]["inputs"]["sampler_name"] = models_config["models"][model]["sampler"]
    prompta["17"]["inputs"]["steps"] = models_config["models"][model]["steps"]
    prompta["17"]["inputs"]["cfg"] = models_config["models"][model]["cfg"]

    ws = websocket.WebSocket()
    ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
    images = await get_images(ws, prompta)

    for node_id in images:
        for image_data in images[node_id]:
            import io
            image = io.BytesIO(image_data)
    f = discord.File(fp=image, filename=f"{prompta['17']['inputs']['seed']}.png")
    embed = discord.Embed(title=f"Here's an image for {interaction.user.display_name}!", description=f"{prompt} - {model}", color = 0xffa500)
    embed.set_image(url=f"attachment://{prompta['17']['inputs']['seed']}.png")
    view = Regenerate(prompt=prompt, model=model, user_id=interaction.user.id, message=interaction)
    await interaction.edit_original_response(content = "", attachments=[f], embed=embed, view=view)
    return

models = []
for model_id, model_data in models_config["models"].items():
    models.append(model_id)

@tree.command(name = "generate", description="Make an image")
async def self(interaction:discord.Interaction, prompt:str, model:typing.Literal[*models], negative:str = ""):
    if interaction.user.id in AUTHORIZED_BOT_USERS:
        prompt = prompt.replace("Felix", "A solo male gray otter with red hair and blue eyes and black ears")
        prompt = prompt.replace("Saekoboyy", "slim anthro grey male wolf with a white belly")
        await generate(interaction, prompt, model, negative)
    else:
        await interaction.response.send_message("No", ephemeral=False)

class Regenerate(discord.ui.View):
    def __init__(self, prompt, model, user_id, message):
        super().__init__()
        self.prompt = prompt
        self.model = model
        self.user_id = user_id
        self.message = message

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.gray, label="Regen")
    async def regenerate(self, interaction:discord.Interaction, button: discord.ui.Button):
        self.stop()
        await generate(interaction, self.prompt, self.model, bad_prompt_words)

    @discord.ui.button(emoji="❌", style=discord.ButtonStyle.gray, label="Delete")
    async def delete(self, interaction:discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.user_id:
            await self.message.delete_original_response()
        else:
            await interaction.channel.send(f"{interaction.user.mention} has requested {self.message.user.mention} to delete the replied message!", reference=self.message)
            await interaction.response.send_message("Thanks for reporting.", ephemeral=True)

@tree.command(name = "dev", description="Developer commands")
async def self(interaction:discord.Interaction, command:typing.Literal["Sync Tree"], input:str = "", input2:str = ""):
    if command == "Sync Tree":
        await tree.sync()
        await interaction.response.send_message("Tree synced successfully!", ephemeral= True)
        
@tree.command(name="kill", description="Shut down the bot (restricted to specific users)")
async def kill(interaction: discord.Interaction):
    if interaction.user.id in AUTHORIZED_KILL_USERS:
        await interaction.response.send_message("oof", ephemeral=False)
        await bot.close()
        return
    else:
        if interaction.user.id == 770518291273089026:
            await interaction.response.send_message("Why kill <@951510569700171867>'s bot?", ephemeral=False)
        else:
            await interaction.response.send_message("ICBM en-route to interaction.user.mention's current location <@951510569700171867>", ephemeral=False)
        
@tree.command(name="restart", description="Restarts the bot (Notice= Front-end only, if back-end crashes then your shit outta luck)")
async def restart(interaction: discord.Interaction):
    if interaction.user.id in AUTHORIZED_RESTART_USERS:
        await interaction.response.send_message("Restarting...", ephemeral=False)
        await bot.close()
        os.execv(sys.executable, ['python'] + sys.argv)
    else:
        await interaction.response.send_message("Sorry but your not allowed to do that, try contacting the dev or his bf to restart :3", ephemeral=True)

bot.run(key)
