[![Static Badge](https://img.shields.io/badge/Telegram-Channel-Link?style=for-the-badge&logo=Telegram&logoColor=white&logoSize=auto&color=blue)](https://t.me/+jJhUfsfFCn4zZDk0)      [![Static Badge](https://img.shields.io/badge/Telegram-Bot%20Link-Link?style=for-the-badge&logo=Telegram&logoColor=white&logoSize=auto&color=blue)](https://t.me/memefi_coin_bot/main?startapp=r_be864a343c)



## Recommendation before use

# 🔥🔥 Use PYTHON 3.10 🔥🔥

## Features

|                           Functional                           | Supported |
|:--------------------------------------------------------------:|:---------:|
|                       Purchasing TapBot                        |     ✅     |
|                        Starting TapBot                         |     ✅     |
|              Claiming TapBot reward every 3 hours              |     ✅     |
|                      Claiming Daily Combo                      |     ✅     |
|                         Multithreading                         |     ✅     |
|                  Binding a proxy to a session                  |     ✅     |
| Auto-purchase of items if you have coins (tap, energy, charge) |     ✅     |
|                Random sleep time between clicks                |     ✅     |
|              Random number of clicks per request               |     ✅     |
|      Referral bonus claiming after first time registering      |     ✅     |
|               Unique User Agent for each session               |     ✅     |
|                Bypassing Cloudflare protection                 |     ✅     |
|             Possibility to specify a referral code             |     ✅     |
|               Displaying the linked Linea wallet               |     ✅     |
|             Display wallet balance in ETH and USD              |     ✅     |
|                     Automated casino game                      |     ✅     |
|     Displaying the status and ticket number in the lottery     |     ✅     |
|            Clear config customization with comments            |     ✅     |
|                   Performing tasks on video                    |     ✅     |
|                   Support telethon .session                    |     ✅     |


## [Settings](https://github.com/SP-l33t/MemeFi-Telethon/blob/main/.env-example)

|            Settings            |                                                                                                                  Description                                                                                                                  |
|:------------------------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|
|     **API_ID / API_HASH**      |                                                                                             Platform data from which to launch a Telegram session                                                                                             |
|     **GLOBAL_CONFIG_PATH**     | Specifies the global path for accounts_config, proxies, sessions. <br/>Specify an absolute path or use an environment variable (default environment variable: **TG_FARM**) <br/>If no environment variable exists, uses the script directory. |
|    **MIN_AVAILABLE_ENERGY**    |                                                                        Minimum amount of available energy, upon reaching which there will be a delay (default **300**)                                                                        |
|    **SLEEP_BY_MIN_ENERGY**     |                                                                                           Delay when reaching minimum energy in seconds ( **300** )                                                                                           |
|     **ADD_TAPS_ON_TURBO**      |                                                                                    How many taps will be added when turbo is activated ( **[500, 1500]** )                                                                                    |
|      **AUTO_UPGRADE_TAP**      |                                                                                                 Should I improve the tap ( True / **False** )                                                                                                 |
|       **MAX_TAP_LEVEL**        |                                                                                                    Maximum level of tap pumping ( **5** )                                                                                                     |
|    **AUTO_UPGRADE_ENERGY**     |                                                                                                 Should I improve the tap ( True / **False** )                                                                                                 |
|      **MAX_ENERGY_LEVEL**      |                                                                                                    Maximum level of tap pumping ( **5** )                                                                                                     |
|    **AUTO_UPGRADE_CHARGE**     |                                                                                                 Should I improve the tap ( True / **False** )                                                                                                 |
|      **MAX_CHARGE_LEVEL**      |                                                                                                    Maximum level of tap pumping ( **3** )                                                                                                     |
|     **APPLY_DAILY_ENERGY**     |                                                                                        Whether to use the daily free energy boost ( **True** / False )                                                                                        |
|     **APPLY_DAILY_TURBO**      |                                                                                        Whether to use the daily free turbo boost ( **True** / False )                                                                                         |
|    **RANDOM_CLICKS_COUNT**     |                                                                                                     Random number of taps ( **[7, 31]** )                                                                                                     |
|     **SLEEP_BETWEEN_TAP**      |                                                                                             Random delay between taps in seconds ( **[19, 36]** )                                                                                             |
|      **AUTO_BUY_TAPBOT**       |                                                                                         Whether to purchase tapbot automatically ( **True** / False )                                                                                         |
|        **ROLL_CASINO**         |                                                                                                Whether to use the casino ( **True** / False )                                                                                                 |
|         **VALUE_SPIN**         |                                                                                                    Number of spins (multiplier) ( **1** )                                                                                                     |
|        **LOTTERY_INFO**        |                                                                                              Displaying lottery information ( **True** / False )                                                                                              |
|        **LINEA_WALLET**        |                                                                                                   Showing Linea purse ( **True** / False )                                                                                                    |
|         **LINEA_API**          |                                                                                            Linea API key to request balance information ( **""** )                                                                                            |
|           **REF_ID**           |                                                                                         Your referral id (part of the referral link after startapp=)                                                                                          |
|        **WATCH_VIDEO**         |                                                                                                 Automatic job execution ( **True** / False )                                                                                                  |
| **RANDOM_SESSION_START_DELAY** |                                                                                        Random delay at session start from 1 to set value (e.g. **30**)                                                                                        |
|     **SESSIONS_PER_PROXY**     |                                                                                            Amount of sessions, that can share same proxy ( **1** )                                                                                            |
|    **USE_PROXY_FROM_FILE**     |                                                                               Whether to use a proxy from the `bot/config/proxies.txt` file (**True** / False)                                                                                |
|   **DISABLE_PROXY_REPLACE**    |                                                                      Disable automatic checking and replacement of non-working proxies before startup (True / **False**)                                                                      |
|       **DEVICE_PARAMS**        |                                                                          Enter device settings to make the telegram session look more realistic  (True / **False**)                                                                           |
|       **DEBUG_LOGGING**        |                                                                                     Whether to log error's tracebacks to /logs folder (True / **False**)                                                                                      |


## Installation

You can download [**Repository**](https://github.com/SP-l33t/MemeFi-Telethon) by cloning it to your system and installing the necessary dependencies:

```shell
~ >>> git clone https://github.com/SP-l33t/MemeFi-Telethon.git
~ >>> cd MemeFi-Telethon

#Linux and MacOS
1. ~/MemeFi-Telethon >>> bash install.sh
2. ~/MemeFi-Telethon >>> bash run.sh

#Windows
1. Run install.bat
2. Run START.bat

OR

~/MemeFi-Telethon >>> python3 -m venv venv
~/MemeFi-Telethon >>> source venv/bin/activate
~/MemeFi-Telethon >>> pip3 install -r requirements.txt
~/MemeFi-Telethon >>> cp .env-example .env
~/MemeFi-Telethon >>> nano .env # Here you must specify your API_ID and API_HASH , the rest is taken by default
~/MemeFi-Telethon >>> python3 main.py

#Windows
1. Double click on INSTALL.bat in MemeFi-Telethon directory to install the dependencies
2. Double click on START.bat in MemeFi-Telethon directory to start the bot

OR

~/MemeFi-Telethon >>> python -m venv venv
~/MemeFi-Telethon >>> venv\Scripts\activate
~/MemeFi-Telethon >>> pip install -r requirements.txt
~/MemeFi-Telethon >>> copy .env-example .env
~/MemeFi-Telethon >>> # Specify your API_ID and API_HASH, the rest is taken by default
~/MemeFi-Telethon >>> python main.py
```

Also for quick launch you can use arguments, for example:

```shell
~/MemeFi-Telethon >>> python3 main.py --action (1/2)
# Or
~/MemeFi-Telethon >>> python3 main.py -a (1/2)

#1 - Run bot
#2 - Create session
```
