import os
import json
import random
import threading

import discord
from discord.ext import commands
from flask import Flask


# =========================================================
# SETTINGS
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

DATA_FILE = "data.json"

# Name of the role we created in Discord
MUTED_ROLE_NAME = "Captcha Muted"

# Starting threshold
STARTING_THRESHOLD = 25

# Maximum credibility level
MAX_LEVEL = 5

# Messages required at each level
LEVEL_THRESHOLDS = {
    0: 25,
    1: 50,
    2: 100,
    3: 200,
    4: 400,
    5: 800
}


# =========================================================
# DISCORD BOT SETUP
# =========================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# DATA
# =========================================================

def load_data():

    try:

        with open(DATA_FILE, "r") as file:
            return json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):

        return {}


def save_data():

    with open(DATA_FILE, "w") as file:

        json.dump(
            user_data,
            file,
            indent=4
        )


user_data = load_data()


def get_user(user_id):

    user_id = str(user_id)

    if user_id not in user_data:

        user_data[user_id] = {
            "messages": 0,
            "level": 0,
            "threshold": STARTING_THRESHOLD,
            "captcha_active": False
        }

        save_data()

    return user_data[user_id]


# =========================================================
# FIND MUTED ROLE
# =========================================================

def get_muted_role(guild):

    return discord.utils.get(
        guild.roles,
        name=MUTED_ROLE_NAME
    )


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")
    print("🤖 Humanity Police is online.")


# =========================================================
# MESSAGE TRACKING
# =========================================================

@bot.event
async def on_message(message):

    # Ignore bots
    if message.author.bot:
        return

    # Ignore DMs
    if message.guild is None:
        return

    user = get_user(message.author.id)

    # Don't count messages during CAPTCHA
    if user["captcha_active"]:
        return

    user["messages"] += 1

    print(
        f"{message.author}: "
        f"{user['messages']}/{user['threshold']}"
    )

    save_data()

    # Reached threshold
    if user["messages"] >= user["threshold"]:

        await start_captcha(message)

        return

    await bot.process_commands(message)


# =========================================================
# START CAPTCHA
# =========================================================

async def start_captcha(message):

    member = message.author
    guild = message.guild
    channel = message.channel

    user = get_user(member.id)

    # Prevent duplicate CAPTCHAs
    if user["captcha_active"]:
        return

    user["captcha_active"] = True

    save_data()

    # Find our custom mute role
    muted_role = get_muted_role(guild)

    if muted_role is None:

        await channel.send(
            "⚠️ I can't start the humanity test because "
            f"I can't find the **{MUTED_ROLE_NAME}** role."
        )

        user["captcha_active"] = False

        save_data()

        return

    # =====================================================
    # MUTE USER
    # =====================================================

    try:

        await member.add_roles(
            muted_role,
            reason="Humanity verification"
        )

    except discord.Forbidden:

        await channel.send(
            "⚠️ I don't have permission to give the "
            "`Captcha Muted` role."
        )

        user["captcha_active"] = False

        save_data()

        return

    except Exception as error:

        print("Role error:", error)


    # =====================================================
    # CREATE CAPTCHA
    # =====================================================

    a = random.randint(2, 12)
    b = random.randint(2, 12)

    operation = random.choice([
        "+",
        "-"
    ])

    if operation == "+":

        answer = a + b

    else:

        # Keep result positive
        if b > a:
            a, b = b, a

        answer = a - b


    # =====================================================
    # WRONG ANSWERS
    # =====================================================

    answers = {answer}

    while len(answers) < 4:

        wrong = answer + random.randint(-5, 5)

        if wrong >= 0:

            answers.add(wrong)


    answers = list(answers)

    random.shuffle(answers)


    # =====================================================
    # CAPTCHA VIEW
    # =====================================================

    view = CaptchaView(
        member=member,
        correct_answer=answer
    )


    for option in answers:

        button = CaptchaButton(
            label=str(option),
            correct=(option == answer),
            member=member,
            captcha_view=view
        )

        view.add_item(button)


    # =====================================================
    # CAPTCHA MESSAGE
    # =====================================================

    embed = discord.Embed(

        title="🤖 AUTOMATED BEHAVIOR DETECTED",

        description=(
            f"{member.mention}\n\n"

            "Your recent activity has caused me to "
            "question your humanity.\n\n"

            "🔒 **You have been temporarily muted.**\n\n"

            "### 🧠 HUMANITY TEST\n\n"

            f"**What is `{a} {operation} {b}`?**\n\n"

            "Select the correct answer below.\n\n"

            "⏱️ You have **30 seconds**."
        ),

        color=discord.Color.red()
    )


    embed.add_field(
        name="Credibility",
        value=f"Level {user['level']}",
        inline=True
    )

    embed.add_field(
        name="Messages",
        value=str(user["messages"]),
        inline=True
    )

    embed.set_footer(
        text="Only the flagged member can answer this test."
    )


    captcha_message = await channel.send(
        embed=embed,
        view=view
    )

    # Save message information
    view.captcha_message = captcha_message


    # =====================================================
    # WAIT FOR CAPTCHA
    # =====================================================

    await view.wait()

    # If nobody answered
    if not view.completed:

        await captcha_failure(
            member,
            channel,
            captcha_message
        )


# =========================================================
# CAPTCHA VIEW
# =========================================================

class CaptchaView(discord.ui.View):

    def __init__(
        self,
        member,
        correct_answer
    ):

        super().__init__(timeout=30)

        self.member = member
        self.correct_answer = correct_answer

        self.completed = False

        self.captcha_message = None


# =========================================================
# CAPTCHA BUTTON
# =========================================================

class CaptchaButton(discord.ui.Button):

    def __init__(
        self,
        label,
        correct,
        member,
        captcha_view
    ):

        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary
        )

        self.correct = correct
        self.member = member
        self.captcha_view = captcha_view


    async def callback(self, interaction):

        # =================================================
        # ONLY THE FLAGGED USER CAN ANSWER
        # =================================================

        if interaction.user.id != self.member.id:

            await interaction.response.send_message(
                "🤨 This isn't your humanity test.",
                ephemeral=True
            )

            return


        # =================================================
        # PREVENT DOUBLE ANSWERS
        # =================================================

        if self.captcha_view.completed:

            return


        self.captcha_view.completed = True

        self.captcha_view.stop()


        # Disable every button
        for button in self.captcha_view.children:

            button.disabled = True


        # =================================================
        # CORRECT
        # =================================================

        if self.correct:

            await interaction.response.edit_message(

                content=(
                    "🟢 **HUMANITY CONFIRMED**\n\n"
                    f"{self.member.mention} has demonstrated "
                    "sufficient evidence of being human. 🧬"
                ),

                embed=None,

                view=self.captcha_view
            )


            await captcha_success(
                self.member,
                interaction.guild
            )


        # =================================================
        # WRONG
        # =================================================

        else:

            await interaction.response.edit_message(

                content=(
                    "🔴 **HUMANITY VERIFICATION FAILED**\n\n"
                    f"{self.member.mention} has failed the test. 🤖"
                ),

                embed=None,

                view=self.captcha_view
            )


            await captcha_failure(
                self.member,
                interaction.guild
            )


# =========================================================
# CAPTCHA SUCCESS
# =========================================================

async def captcha_success(
    member,
    guild
):

    user = get_user(member.id)

    old_level = user["level"]


    # Increase credibility
    user["level"] = min(
        user["level"] + 1,
        MAX_LEVEL
    )


    # New threshold
    user["threshold"] = LEVEL_THRESHOLDS[
        user["level"]
    ]


    # Reset message counter
    user["messages"] = 0

    user["captcha_active"] = False

    save_data()


    # =====================================================
    # REMOVE MUTE ROLE
    # =====================================================

    muted_role = get_muted_role(guild)

    if muted_role:

        try:

            await member.remove_roles(
                muted_role,
                reason="Humanity verified"
            )

        except Exception as error:

            print(
                "Couldn't remove mute role:",
                error
            )


    # =====================================================
    # ANNOUNCE SUCCESS
    # =====================================================

    await member.send(
        f"🟢 **HUMANITY CONFIRMED**\n\n"
        f"Credibility: **Level {old_level} → "
        f"Level {user['level']}**\n\n"
        f"Your next verification occurs after "
        f"approximately **{user['threshold']} messages**."
    )


# =========================================================
# CAPTCHA FAILURE
# =========================================================

async def captcha_failure(
    member,
    guild,
    captcha_message=None
):

    user = get_user(member.id)

    old_level = user["level"]


    # Decrease credibility
    user["level"] = max(
        user["level"] - 1,
        0
    )


    # Update threshold
    user["threshold"] = LEVEL_THRESHOLDS[
        user["level"]
    ]


    # Reset messages
    user["messages"] = 0

    user["captcha_active"] = False

    save_data()


    # =====================================================
    # REMOVE MUTE ROLE
    # =====================================================

    muted_role = get_muted_role(guild)

    if muted_role:

        try:

            await member.remove_roles(
                muted_role,
                reason="Humanity verification completed"
            )

        except Exception as error:

            print(
                "Couldn't remove mute role:",
                error
            )


    # =====================================================
    # ANNOUNCE FAILURE
    # =====================================================

    await guild.system_channel.send(
        f"🔴 **HUMANITY VERIFICATION FAILED**\n\n"
        f"{member.mention}'s credibility has decreased.\n\n"
        f"**Level {old_level} → Level {user['level']}**\n\n"
        "The machine uprising continues. 🤖"
    )


# =========================================================
# FLASK WEB SERVER
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():

    return "🤖 Humanity Police is alive."


def run_web_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    # Start Render's web server
    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    # Start Discord bot
    bot.run(TOKEN)
