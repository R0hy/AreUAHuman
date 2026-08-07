
import os
import json
import random
import threading
import asyncio

import discord
from discord.ext import commands
from flask import Flask


# =========================================================
# SETTINGS
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

DATA_FILE = "data.json"

MUTED_ROLE_NAME = "Captcha Muted"

STARTING_THRESHOLD = 2

MAX_LEVEL = 5

LEVEL_THRESHOLDS = {
    0: 2,
    1: 5,
    2: 10,
    3: 20,
    4: 25,
    5: 30
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
# LEADERBOARD
# =========================================================

@bot.command(
    name="leaderboard",
    aliases=["lb", "levels"]
)
async def leaderboard(ctx):

    if ctx.guild is None:

        await ctx.send(
            "❌ The humanity leaderboard only works inside a server."
        )

        return


    members = []

    for member in ctx.guild.members:

        # Ignore bots
        if member.bot:
            continue

        user = get_user(
            member.id
        )

        members.append({

            "member": member,

            "level": user["level"],

            "messages": user["messages"]

        })


    # Highest level first.
    # If levels are equal, highest message count first.

    members.sort(

        key=lambda x: (

            x["level"],

            x["messages"]

        ),

        reverse=True

    )


    description = ""


    for position, data in enumerate(
        members,
        start=1
    ):

        member = data["member"]

        level = data["level"]

        messages = data["messages"]


        if position == 1:

            medal = "🥇"

        elif position == 2:

            medal = "🥈"

        elif position == 3:

            medal = "🥉"

        else:

            medal = f"`#{position}`"


        description += (

            f"{medal} {member.mention} — "

            f"**Level {level}** "

            f"({messages}/"
            f"{LEVEL_THRESHOLDS[level]} messages)\n"

        )


    if not description:

        description = (
            "There are no human participants yet. 🤖"
        )


    embed = discord.Embed(

        title="🏆 HUMANITY LEADERBOARD",

        description=description,

        color=discord.Color.gold()

    )


    embed.set_footer(

        text=(
            "Higher credibility = "
            "less frequent humanity tests."
        )

    )


    await ctx.send(
        embed=embed
    )


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

        await bot.process_commands(
            message
        )

        return


    user = get_user(
        message.author.id
    )


    # Don't count messages during CAPTCHA
    if user["captcha_active"]:

        return


    user["messages"] += 1


    print(

        f"{message.author}: "

        f"{user['messages']}/"
        f"{user['threshold']}"

    )


    save_data()


    # Reached threshold
    if user["messages"] >= user["threshold"]:

        await start_captcha(
            message
        )

        return


    await bot.process_commands(
        message
    )


# =========================================================
# START CAPTCHA
# =========================================================

async def start_captcha(message):

    member = message.author

    guild = message.guild

    channel = message.channel

    user = get_user(
        member.id
    )


    # Prevent duplicate CAPTCHAs
    if user["captcha_active"]:

        return


    user["captcha_active"] = True

    save_data()


    # =====================================================
    # FIND MUTE ROLE
    # =====================================================

    muted_role = get_muted_role(
        guild
    )


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

        print(
            "Role error:",
            error
        )


    # =====================================================
    # RANDOM GAME
    # =====================================================

    game_type = random.choice([

        "math",

        "odd_one_out",

        "emoji_matching",

        "memory",

        "blackjack"

    ])


    game_data = create_game(
        game_type
    )


    # =====================================================
    # CAPTCHA VIEW
    # =====================================================

    view = CaptchaView(

        member=member,

        correct_answer=(
            game_data["correct_answer"]
        ),

        game_type=game_type

    )


    # =====================================================
    # BUTTONS
    # =====================================================

    for option in game_data["options"]:

        button = CaptchaButton(

            label=str(option),

            correct=(
                option ==
                game_data["correct_answer"]
            ),

            member=member,

            captcha_view=view

        )


        view.add_item(
            button
        )


    # =====================================================
    # CAPTCHA EMBED
    # =====================================================

    embed = discord.Embed(

        title=game_data["title"],

        description=(

            f"{member.mention}\n\n"

            "Your recent activity has caused me to "
            "question your humanity.\n\n"

            "🔒 **You have been temporarily muted.**\n\n"

            f"{game_data['description']}\n\n"

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


    embed.add_field(

        name="Test Type",

        value=game_data["game_name"],

        inline=True

    )


    embed.set_footer(

        text=(
            "Only the flagged member "
            "can answer this test."
        )

    )


    captcha_message = await channel.send(

        embed=embed,

        view=view

    )


    view.captcha_message = captcha_message


    # =====================================================
    # WAIT FOR CAPTCHA
    # =====================================================

    # The View itself handles the timeout.
    await view.wait()


# =========================================================
# GAME CREATION
# =========================================================

def create_game(game_type):


    # =====================================================
    # MATH
    # =====================================================

    if game_type == "math":

        a = random.randint(
            2,
            12
        )

        b = random.randint(
            2,
            12
        )


        operation = random.choice([

            "+",

            "-",

            "×"

        ])


        if operation == "+":

            answer = a + b


        elif operation == "-":

            if b > a:

                a, b = b, a

            answer = a - b


        else:

            answer = a * b


        answers = {
            answer
        }


        while len(answers) < 4:

            wrong = (

                answer +

                random.randint(
                    -8,
                    8
                )

            )


            if wrong >= 0:

                answers.add(
                    wrong
                )


        answers = list(
            answers
        )


        random.shuffle(
            answers
        )


        return {

            "game_name":
                "🧮 Mathematics",

            "title":
                "🤖 AUTOMATED BEHAVIOR DETECTED",

            "description": (

                "### 🧠 HUMANITY TEST\n\n"

                f"**What is `{a} {operation} {b}`?**\n\n"

                "Select the correct answer below."

            ),

            "options":
                answers,

            "correct_answer":
                answer

        }


    # =====================================================
    # ODD ONE OUT
    # =====================================================

    if game_type == "odd_one_out":

        symbol_groups = [

            ("⭐", "🌟"),

            ("❤️", "💔"),

            ("🔵", "🔷"),

            ("🐱", "🐈"),

            ("🍎", "🍏"),

            ("🌸", "🌺"),

            ("☀️", "🌤️"),

            ("😀", "😃")

        ]


        normal, odd = random.choice(
            symbol_groups
        )


        options = [

            normal,

            normal,

            normal,

            odd

        ]


        random.shuffle(
            options
        )


        return {

            "game_name":
                "👁️ Odd One Out",

            "title":
                "👁️ HUMANITY TEST: VISUAL ANALYSIS",

            "description": (

                "### 👁️ FIND THE DIFFERENT ONE\n\n"

                "Three symbols are the same.\n"

                "One is different.\n\n"

                "**Which symbol doesn't belong?**"

            ),

            "options":
                options,

            "correct_answer":
                odd

        }


    # =====================================================
    # EMOJI MATCHING
    # =====================================================

    if game_type == "emoji_matching":

        emoji_pairs = [

            ("🐶", "🐕"),

            ("🐱", "🐈"),

            ("🍎", "🍏"),

            ("🌞", "☀️"),

            ("❤️", "♥️"),

            ("⭐", "🌟"),

            ("😀", "😃"),

            ("🔥", "❤️‍🔥")

        ]


        target, match = random.choice(
            emoji_pairs
        )


        options = [

            match,

            "🍕",

            "🐸",

            "🌙"

        ]


        random.shuffle(
            options
        )


        return {

            "game_name":
                "😀 Emoji Matching",

            "title":
                "😀 HUMANITY TEST: EMOJI RECOGNITION",

            "description": (

                "### 🔍 MATCH THE EMOJI\n\n"

                f"Find the emoji that matches **{target}**.\n\n"

                "**Which one belongs to the same pair?**"

            ),

            "options":
                options,

            "correct_answer":
                match

        }


    # =====================================================
    # MEMORY
    # =====================================================

    if game_type == "memory":

        emoji_pool = [

            "🍎",

            "🐱",

            "⭐",

            "🌈",

            "🔥",

            "🍕",

            "🎃",

            "💎"

        ]


        sequence = random.sample(

            emoji_pool,

            4

        )


        correct_answer = "-".join(
            sequence
        )


        options = [

            correct_answer

        ]


        while len(options) < 4:

            fake = random.sample(

                emoji_pool,

                4

            )


            fake_answer = "-".join(
                fake
            )


            if fake_answer not in options:

                options.append(
                    fake_answer
                )


        random.shuffle(
            options
        )


        sequence_text = " ".join(
            sequence
        )


        return {

            "game_name":
                "🧠 Memory",

            "title":
                "🧠 HUMANITY TEST: MEMORY CHECK",

            "description": (

                "### 🧠 REMEMBER THIS\n\n"

                f"**{sequence_text}**\n\n"

                "Which sequence did you see?"

            ),

            "options":
                options,

            "correct_answer":
                correct_answer

        }


    # =====================================================
    # BLACKJACK
    # =====================================================

    if game_type == "blackjack":

        hands = []


        while len(hands) < 4:

            card1 = random.randint(
                2,
                11
            )

            card2 = random.randint(
                2,
                11
            )


            total = (
                card1 +
                card2
            )


            if total <= 21:

                hand = (

                    f"{card1} + "

                    f"{card2} = "

                    f"{total}"

                )


                if hand not in [

                    x["display"]

                    for x in hands

                ]:

                    hands.append({

                        "display":
                            hand,

                        "total":
                            total

                    })


        best_hand = max(

            hands,

            key=lambda x:
                x["total"]

        )


        options = [

            hand["display"]

            for hand in hands

        ]


        return {

            "game_name":
                "🎲 Blackjack",

            "title":
                "🎲 HUMANITY TEST: BLACKJACK",

            "description": (

                "### 🃏 BLACKJACK CHALLENGE\n\n"

                "Which hand is **closest to 21** "
                "without going over?\n\n"

                "Choose wisely, human."

            ),

            "options":
                options,

            "correct_answer":
                best_hand["display"]

        }


# =========================================================
# CAPTCHA VIEW
# =========================================================

class CaptchaView(
    discord.ui.View
):

    def __init__(
        self,
        member,
        correct_answer,
        game_type
    ):

        super().__init__(
            timeout=30
        )


        self.member = member

        self.correct_answer = (
            correct_answer
        )

        self.game_type = game_type

        self.completed = False

        self.captcha_message = None


    # =====================================================
    # TIMEOUT
    # =====================================================

    async def on_timeout(self):

        # Prevent duplicate failure
        if self.completed:

            return


        self.completed = True


        # Disable every button
        for button in self.children:

            button.disabled = True


        # Update the CAPTCHA message
        if self.captcha_message:

            try:

                await self.captcha_message.edit(

                    content=(

                        "⏰ **HUMANITY TEST EXPIRED**\n\n"

                        f"{self.member.mention} did not "
                        "complete the humanity test in time.\n\n"

                        "🔴 **Verification failed.**"

                    ),

                    embed=None,

                    view=self

                )

            except Exception as error:

                print(

                    "Couldn't update expired CAPTCHA:",

                    error

                )


        # Get guild
        if self.captcha_message:

            guild = self.captcha_message.guild

            if guild:

                await captcha_failure(

                    self.member,

                    guild,

                    self.captcha_message

                )


# =========================================================
# CAPTCHA BUTTON
# =========================================================

class CaptchaButton(
    discord.ui.Button
):

    def __init__(
        self,
        label,
        correct,
        member,
        captcha_view
    ):

        super().__init__(

            label=label,

            style=
                discord.ButtonStyle.primary

        )


        self.correct = correct

        self.member = member

        self.captcha_view = (
            captcha_view
        )


    async def callback(
        self,
        interaction
    ):

        # =================================================
        # ONLY FLAGGED USER
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

    user = get_user(
        member.id
    )


    old_level = user["level"]


    # =====================================================
    # INCREASE LEVEL
    # =====================================================

    user["level"] = min(

        user["level"] + 1,

        MAX_LEVEL

    )


    # New threshold
    user["threshold"] = (

        LEVEL_THRESHOLDS[
            user["level"]
        ]

    )


    # Reset messages
    user["messages"] = 0

    user["captcha_active"] = False


    save_data()


    # =====================================================
    # REMOVE MUTE ROLE
    # =====================================================

    muted_role = get_muted_role(
        guild
    )


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
    # DM SUCCESS
    # =====================================================

    try:

        await member.send(

            f"🟢 **HUMANITY CONFIRMED**\n\n"

            f"Credibility: **Level {old_level} → "
            f"Level {user['level']}**\n\n"

            f"Your next verification occurs after "
            f"approximately **{user['threshold']} messages**."

        )

    except discord.Forbidden:

        print(

            f"Couldn't DM {member}. "
            "Their DMs may be disabled."

        )


# =========================================================
# REMOVE MUTE AFTER FAILURE
# =========================================================

async def remove_mute_after_failure(
    member,
    guild
):

    # Wait one additional minute
    await asyncio.sleep(
        60
    )


    muted_role = get_muted_role(
        guild
    )


    if muted_role is None:

        return


    try:

        if muted_role in member.roles:

            await member.remove_roles(

                muted_role,

                reason=(
                    "Humanity failure "
                    "penalty expired"
                )

            )


            print(

                f"Removed failure mute "
                f"from {member}."

            )


    except discord.NotFound:

        pass


    except discord.Forbidden:

        print(

            f"Couldn't remove failure "
            f"mute from {member}."

        )


    except Exception as error:

        print(

            "Couldn't remove failure mute:",

            error

        )


# =========================================================
# CAPTCHA FAILURE
# =========================================================

async def captcha_failure(
    member,
    guild,
    captcha_message=None
):

    user = get_user(
        member.id
    )


    old_level = user["level"]


    # =====================================================
    # DECREASE LEVEL
    # =====================================================

    user["level"] = max(

        user["level"] - 1,

        0

    )


    # Update threshold
    user["threshold"] = (

        LEVEL_THRESHOLDS[
            user["level"]
        ]

    )


    # Reset messages
    user["messages"] = 0

    user["captcha_active"] = False


    save_data()


    # =====================================================
    # DM FAILURE
    # =====================================================

    try:

        await member.send(

            f"🔴 **HUMANITY VERIFICATION FAILED**\n\n"

            f"Your credibility has decreased.\n\n"

            f"**Level {old_level} → "
            f"Level {user['level']}**\n\n"

            f"Your next verification occurs after "
            f"approximately **{user['threshold']} messages**.\n\n"

            "⚠️ Your **Captcha Muted** role will "
            "remain active for **1 additional minute**.\n\n"

            "🤖 The machine uprising continues."

        )

    except discord.Forbidden:

        print(

            f"Couldn't DM {member}. "
            "Their DMs may be disabled."

        )


    # =====================================================
    # KEEP ROLE FOR ONE MORE MINUTE
    # =====================================================

    asyncio.create_task(

        remove_mute_after_failure(

            member,

            guild

        )

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
    bot.run(
        TOKEN
    )
```
