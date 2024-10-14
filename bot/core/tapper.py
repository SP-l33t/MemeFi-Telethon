import aiohttp
import asyncio
import os
import random
import json
from urllib.parse import unquote, parse_qs
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from datetime import datetime, timezone
from dateutil import parser
from time import time

from opentele.tl import TelegramClient
from telethon.errors import *
from telethon.types import InputBotAppShortName, InputUser
from telethon.functions import messages

from bot.config import settings
from bot.utils import logger, log_error, proxy_utils, config_utils, AsyncInterProcessLock, CONFIG_PATH
from bot.utils.graphql import Query, OperationName
from bot.utils.boosts import FreeBoostType, UpgradableBoostType
from bot.exceptions import InvalidSession, InvalidProtocol
from .headers import headers, get_sec_ch_ua
from .TLS import TLSv1_3_BYPASS


class Tapper:
    def __init__(self, tg_client: TelegramClient):
        self.tg_client = tg_client
        self.session_name, _ = os.path.splitext(os.path.basename(tg_client.session.filename))
        self.lock = AsyncInterProcessLock(
            os.path.join(os.path.dirname(CONFIG_PATH), 'lock_files', f"{self.session_name}.lock"))
        self.headers = headers

        session_config = config_utils.get_session_config(self.session_name, CONFIG_PATH)

        if not all(key in session_config for key in ('api', 'user_agent')):
            logger.critical(self.log_message('CHECK accounts_config.json as it might be corrupted'))
            exit(-1)

        user_agent = session_config.get('user_agent')
        self.headers['user-agent'] = user_agent
        self.headers.update(**get_sec_ch_ua(user_agent))

        self.proxy = session_config.get('proxy')
        if self.proxy:
            proxy = Proxy.from_str(self.proxy)
            proxy_dict = proxy_utils.to_telethon_proxy(proxy)
            self.tg_client.set_proxy(proxy_dict)

        self.GRAPHQL_URL = 'https://api-gw-tg.memefi.club/graphql'

        self._webview_data = None

    def log_message(self, message) -> str:
        return f"<ly>{self.session_name}</ly> | {message}"

    async def initialize_webview_data(self):
        if not self._webview_data:
            while True:
                try:
                    peer = await self.tg_client.get_input_entity('memefi_coin_bot')
                    bot_id = InputUser(user_id=peer.user_id, access_hash=peer.access_hash)
                    input_bot_app = InputBotAppShortName(bot_id=bot_id, short_name="main")
                    self._webview_data = {'peer': peer, 'app': input_bot_app}
                    break
                except FloodWaitError as fl:
                    logger.warning(self.log_message(f"FloodWait {fl}. Waiting {fl.seconds}s"))
                    await asyncio.sleep(fl.seconds + 3)
                except (UnauthorizedError, AuthKeyUnregisteredError):
                    raise InvalidSession(f"{self.session_name}: User is unauthorized")
                except (UserDeactivatedError, UserDeactivatedBanError, PhoneNumberBannedError):
                    raise InvalidSession(f"{self.session_name}: User is banned")

    async def get_tg_web_data(self):
        if self.proxy and not self.tg_client._proxy:
            logger.critical(self.log_message('Proxy found, but not passed to TelegramClient'))
            exit(-1)
        json_data = ""
        async with self.lock:
            try:
                if not self.tg_client.is_connected():
                    await self.tg_client.connect()
                await self.initialize_webview_data()
                await asyncio.sleep(random.uniform(1, 2))

                ref_id = settings.REF_ID if random.randint(0, 100) <= 85 else "r_be864a343c"

                web_view = await self.tg_client(messages.RequestAppWebViewRequest(
                    **self._webview_data,
                    platform='android',
                    write_allowed=True,
                    start_param=ref_id
                ))

                auth_url = web_view.url
                tg_web_data = parse_qs(unquote(
                    auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0]))

                user_data = json.loads(tg_web_data.get('user', [''])[0])
                chat_instance = tg_web_data.get('chat_instance', [''])[0]
                chat_type = tg_web_data.get('chat_type', [''])[0]
                start_param = tg_web_data.get('start_param', [''])[0]
                auth_date = tg_web_data.get('auth_date', [''])[0]
                hash_value = tg_web_data.get('hash', [''])[0]
                json_string = json.dumps(user_data, separators=(',', ':'))

                json_data = {
                    "operationName": OperationName.MutationTelegramUserLogin,
                    "variables": {
                        "webAppData": {
                            "auth_date": int(auth_date),
                            "hash": hash_value,
                            "query_id": "",
                            "checkDataString": f'auth_date={auth_date}\nchat_instance={chat_instance}\nchat_type={chat_type}\nstart_param={start_param}\nuser={json_string}',
                            "user": {
                                "id": user_data['id'],
                                "allows_write_to_pm": user_data['allows_write_to_pm'],
                                "first_name": user_data['first_name'],
                                "last_name": user_data.get('last_name', ''),
                                "username": user_data.get('username', ''),
                                "language_code": user_data.get('language_code', 'en')
                            }
                        }
                    },
                    "query": Query.MutationTelegramUserLogin
                }
                # with open('out.txt', 'w+') as file:
                #     json.dump(json_data, file)
            except InvalidSession:
                raise

            except Exception as error:
                log_error(self.log_message(f"Unknown error during Authorization: {type(error).__name__}"))
                await asyncio.sleep(delay=3)

            finally:
                if self.tg_client.is_connected():
                    await self.tg_client.disconnect()
                    await asyncio.sleep(15)

        return json_data

    async def check_proxy(self, http_client: CloudflareScraper) -> bool:
        proxy_conn = http_client.connector
        if proxy_conn and not hasattr(proxy_conn, '_proxy_host'):
            logger.info(self.log_message(f"Running Proxy-less"))
            return True
        try:
            response = await http_client.get(url='https://ifconfig.me/ip', timeout=aiohttp.ClientTimeout(15))
            logger.info(self.log_message(f"Proxy IP: {await response.text()}"))
            return True
        except Exception as error:
            proxy_url = f"{proxy_conn._proxy_type}://{proxy_conn._proxy_host}:{proxy_conn._proxy_port}"
            log_error(self.log_message(f"Proxy: {proxy_url} | Error: {type(error).__name__}"))
            return False

    async def get_access_token(self, http_client: CloudflareScraper, tg_web_data: dict[str]):
        for _ in range(2):
            try:
                response = await http_client.post(url=self.GRAPHQL_URL, json=tg_web_data)
                response.raise_for_status()

                response_json = await response.json()

                if 'errors' in response_json:
                    raise InvalidProtocol(f'get_access_token msg: {response_json["errors"][0]["message"]}')

                access_token = response_json.get('data', {}).get('telegramUserLogin', {}).get('access_token', '')

                if not access_token:
                    await asyncio.sleep(delay=5)
                    continue

                return access_token
            except Exception as error:
                log_error(self.log_message(f"❗️ Unknown error while getting Access Token: {error}"))
                await asyncio.sleep(delay=15)

        return ""

    async def get_telegram_me(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.QueryTelegramUserMe,
                'query': Query.QueryTelegramUserMe,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            response_json = await response.json()

            if 'errors' in response_json:
                raise InvalidProtocol(f'get_telegram_me msg: {response_json["errors"][0]["message"]}')

            me = response_json['data']['telegramUserMe']

            return me
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error while getting Telegram Me: {error}"))
            await asyncio.sleep(delay=3)

            return {}

    async def get_profile_data(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.QUERY_GAME_CONFIG,
                'query': Query.QUERY_GAME_CONFIG,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()
            response_json = await response.json()

            if 'errors' in response_json:
                raise InvalidProtocol(f'get_profile_data msg: {response_json["errors"][0]["message"]}')

            profile_data = response_json['data']['telegramGameGetConfig']

            return profile_data
        except Exception as error:
            log_error(self.log_message(f"❗️Unknown error while getting Profile Data: {error}"))
            await asyncio.sleep(delay=9)

    async def set_next_boss(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.telegramGameSetNextBoss,
                'query': Query.telegramGameSetNextBoss,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()
            response_json = await response.json()

            return True
        except Exception as error:
            log_error(self.log_message(f"❗️Unknown error while Setting Next Boss: {error}"))
            await asyncio.sleep(delay=9)

            return False

    async def get_clan(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.ClanMy,
                'query': Query.ClanMy,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()
            response_json = await response.json()

            data = response_json['data']['clanMy']
            if data and data['id']:
                return data['id']
            else:
                return False

        except Exception as error:
            log_error(self.log_message(f"❗️Unknown error while get clan: {error}"))
            await asyncio.sleep(delay=9)
            return False

    async def leave_clan(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.Leave,
                'query': Query.Leave,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()
            response_json = await response.json()
            if response_json['data']:
                if response_json['data']['clanActionLeaveClan']:
                    return True

        except Exception as error:
            log_error(self.log_message(f"❗️Unknown error while clan leave: {error}"))
            await asyncio.sleep(delay=9)
            return False

    async def join_clan(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.Join,
                'query': Query.Join,
                'variables': {
                    'clanId': '71886d3b-1186-452d-8ac6-dcc5081ab204'
                }
            }

            while True:
                response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
                response.raise_for_status()
                response_json = await response.json()
                if response_json['data']:
                    if response_json['data']['clanActionJoinClan']:
                        return True
                elif response_json['errors']:
                    await asyncio.sleep(2)
                    return False
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error while clan join: {error}"))
            await asyncio.sleep(delay=9)
            return False

    async def get_bot_config(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.TapbotConfig,
                'query': Query.TapbotConfig,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            response_json = await response.json()
            bot_config = response_json['data']['telegramGameTapbotGetConfig']

            return bot_config
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error while getting Bot Config: {error}"))
            await asyncio.sleep(delay=9)

    async def start_bot(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.TapbotStart,
                'query': Query.TapbotStart,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            return True
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error while Starting Bot: {error}"))
            await asyncio.sleep(delay=9)

            return False

    async def claim_bot(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.TapbotClaim,
                'query': Query.TapbotClaim,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()
            response_json = await response.json()
            data = response_json['data']["telegramGameTapbotClaim"]
            return {"isClaimed": False, "data": data}
        except Exception as error:
            return {"isClaimed": True, "data": None}

    async def claim_referral_bonus(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.Mutation,
                'query': Query.Mutation,
                'variables': {}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            return True
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error while Claiming Referral Bonus: {error}"))
            await asyncio.sleep(delay=9)

            return False

    async def apply_boost(self, http_client: CloudflareScraper, boost_type: FreeBoostType):
        try:
            json_data = {
                'operationName': OperationName.telegramGameActivateBooster,
                'query': Query.telegramGameActivateBooster,
                'variables': {
                    'boosterType': boost_type
                }
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            return True
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error while Apply {boost_type} Boost: {error}"))
            await asyncio.sleep(delay=9)

            return False

    async def upgrade_boost(self, http_client: CloudflareScraper, boost_type: UpgradableBoostType):
        try:
            json_data = {
                'operationName': OperationName.telegramGamePurchaseUpgrade,
                'query': Query.telegramGamePurchaseUpgrade,
                'variables': {
                    'upgradeType': boost_type
                }
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            response_json = await response.json()

            if 'errors' in response_json:
                raise InvalidProtocol(f'upgrade_boost msg: {response_json["errors"][0]["message"]}')

            return True
        except Exception:
            return False

    async def send_taps(self, http_client: CloudflareScraper, nonce: str, taps: int):
        try:
            vectorArray = []
            for tap in range(taps):
                """ check if tap is greater than 4 or less than 1 and set tap to random number between 1 and 4"""
                if tap > 4 or tap < 1:
                    tap = random.randint(1, 4)
                vectorArray.append(tap)

            vector = ",".join(str(x) for x in vectorArray)
            json_data = {
                'operationName': OperationName.MutationGameProcessTapsBatch,
                'query': Query.MutationGameProcessTapsBatch,
                'variables': {
                    'payload': {
                        'nonce': nonce,
                        'tapsCount': taps,
                        'vector': vector
                    },
                }
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            response_json = await response.json()

            if response.status != 200:
                status500 = response.status
                return status500

            if 'errors' in response_json:
                raise InvalidProtocol(f'send_taps msg: {response_json["errors"][0]["message"]}')

            profile_data = response_json['data']['telegramGameProcessTapsBatch']
            return profile_data
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error when Tapping: {error}"))
            await asyncio.sleep(delay=9)

    async def play_slotmachine(self, http_client: CloudflareScraper):
        spin_value = settings.VALUE_SPIN
        try:
            json_data = {
                'operationName': OperationName.SpinSlotMachine,
                'query': Query.SpinSlotMachine,
                'variables': {
                    'payload': {
                        'spinsCount': spin_value
                    }
                }
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response_json = await response.json()
            play_data = response_json.get('data', {}).get('slotMachineSpinV2', {})

            return play_data
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error when Play Casino: {error}"))
            return {}

    async def wallet_check(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': OperationName.TelegramMemefiWallet,
                'query': Query.TelegramMemefiWallet,
                'variables': {}
            }
            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response_json = await response.json()
            no_wallet_response = {'data': {'telegramMemefiWallet': None}}
            if response_json == no_wallet_response:
                return "-"
            else:
                linea_wallet = response_json.get('data', {}).get('telegramMemefiWallet', {}).get('walletAddress', {})
                return linea_wallet
        except Exception as error:
            log_error(self.log_message(f"❗️ Unknown error when Get Wallet: {error}"))
            return None

    async def get_linea_wallet_balance(self, http_client: CloudflareScraper, linea_wallet: str):
        try:
            api_key = settings.LINEA_API
            api_url = (f"https://api.lineascan.build/api?module=account&action=balance&address="
                       f"{linea_wallet}&tag=latest&apikey={api_key}")

            async with http_client.get(api_url) as response:
                data = await response.json()
                if data['status'] == '1' and data['message'] == 'OK':
                    balance_wei = int(data['result'])
                    balance_eth = float((balance_wei / 1e18))
                    return balance_eth
                else:
                    if linea_wallet == '-':
                        balance_eth = '-'
                        return balance_eth
                    else:
                        logger.warning(self.log_message(f"Failed to retrieve Linea wallet balance: {data['message']}"))
                        return None
        except Exception as error:
            log_error(self.log_message(f"Error getting Linea wallet balance: {error}"))
            return None

    async def get_eth_price(self, http_client: CloudflareScraper, balance_eth: str):
        try:
            if balance_eth == '-':
                return balance_eth
            else:
                api_url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=ethereum"

                async with http_client.get(api_url) as response:
                    data = await response.json()
                    if response.status == 200:
                        eth_current_price = int(float(data[0]['current_price']) // 1)
                        eth_price = round((eth_current_price * float(balance_eth)), 2)
                        return eth_price
                    else:
                        logger.warning(self.log_message(f"Failed to retrieve ETH price: {response.status} code"))
                        return None
        except Exception as error:
            log_error(self.log_message(f"Error getting ETH price: {error}"))
            return None

    async def get_campaigns(self, http_client: CloudflareScraper):
        try:
            json_data = {
                'operationName': "CampaignLists",
                'query': Query.CampaignLists,
                'variables': {}
            }
            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            data = await response.json()

            if 'errors' in data:
                logger.error(self.log_message(f"Error while getting campaigns: {data['errors'][0]['message']}"))
                return None

            campaigns = data.get('data', {}).get('campaignLists', {}).get('normal', [])
            return [campaign for campaign in campaigns if 'youtube' in campaign.get('description', '').lower()]

        except Exception as e:
            log_error(self.log_message(f"Unknown error while getting campaigns: {str(e)}"))
            return {}

    async def get_tasks_list(self, http_client: CloudflareScraper, campaigns_id: str):
        try:
            json_data = {
                'operationName': "GetTasksList",
                'query': Query.GetTasksList,
                'variables': {'campaignId': campaigns_id}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            data = await response.json()

            if 'errors' in data:
                logger.error(self.log_message(f"Error while getting tasks: {data['errors'][0]['message']}"))
                return None

            return data.get('data', {}).get('campaignTasks', [])

        except Exception as e:
            log_error(self.log_message(f"Unknown error while getting tasks: {str(e)}"))
            return None

    async def verify_campaign(self, http_client: CloudflareScraper, task_id: str):
        try:
            json_data = {
                'operationName': "CampaignTaskToVerification",
                'query': Query.CampaignTaskToVerification,
                'variables': {'taskConfigId': task_id}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            data = await response.json()

            if 'errors' in data:
                logger.error(self.log_message(f"Error while verifying task: {data['errors'][0]['message']}"))
                return None

            return data.get('data', {}).get('campaignTaskMoveToVerificationV2')
        except Exception as e:
            log_error(self.log_message(f"Unknown error while verifying task: {str(e)}"))
            return None

    async def get_task_by_id(self, http_client: CloudflareScraper, task_id: str):
        try:
            json_data = {
                'operationName': "GetTaskById",
                'query': Query.GetTaskById,
                'variables': {'taskId': task_id}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)
            response.raise_for_status()

            data = await response.json()

            if 'errors' in data:
                logger.error(self.log_message(f"Error while getting task by id: {data['errors'][0]['message']}"))
                return None

            return data.get('data', {}).get('campaignTaskGetConfig')
        except Exception as e:
            log_error(self.log_message(f"Unknown error while getting task by id: {str(e)}"))
            return None

    async def complete_task(self, http_client: CloudflareScraper, user_task_id: str):
        try:
            json_data = {
                'operationName': "CampaignTaskMarkAsCompleted",
                'query': Query.CampaignTaskMarkAsCompleted,
                'variables': {'userTaskId': user_task_id}
            }

            response = await http_client.post(url=self.GRAPHQL_URL, json=json_data)

            response.raise_for_status()

            data = await response.json()

            if 'errors' in data:
                logger.error(self.log_message(f"Error while completing task: {data['errors'][0]['message']}"))
                return None

            return data.get('data', {}).get('campaignTaskMarkAsCompleted')

        except Exception as e:
            log_error(self.log_message(f"Unknown error while completing task: {str(e)}"))
            return None

    async def run(self):
        random_delay = random.uniform(1, settings.RANDOM_SESSION_START_DELAY)
        logger.info(self.log_message(f"Bot will start in <light-red>{int(random_delay)}s</light-red>"))
        await asyncio.sleep(delay=random_delay)

        access_token_created_time = 0
        turbo_time = 0
        active_turbo = False

        ssl_context = TLSv1_3_BYPASS.create_ssl_context()
        proxy_conn = {'connector': ProxyConnector.from_url(self.proxy, ssl=ssl_context)} if self.proxy else {}
        async with CloudflareScraper(headers=self.headers, timeout=aiohttp.ClientTimeout(60),
                                     **proxy_conn) as http_client:
            while True:
                if not await self.check_proxy(http_client=http_client):
                    logger.warning(self.log_message('Failed to connect to proxy server. Sleep 5 minutes.'))
                    await asyncio.sleep(300)
                    continue

                noBalance = False
                try:
                    if time() - access_token_created_time >= 5400:
                        http_client.headers.pop("Authorization", None)
                        tg_web_data = await self.get_tg_web_data()

                        if not tg_web_data:
                            logger.warning(self.log_message('Failed to get webview URL'))
                            await asyncio.sleep(300)
                            continue

                        access_token = await self.get_access_token(http_client=http_client, tg_web_data=tg_web_data)

                        if not access_token:
                            await asyncio.sleep(delay=5)
                            continue

                        http_client.headers["Authorization"] = f"Bearer {access_token}"

                        access_token_created_time = time()

                        await self.get_telegram_me(http_client=http_client)

                        profile_data = await self.get_profile_data(http_client=http_client)

                        if not profile_data:
                            continue

                        balance = profile_data.get('coinsAmount', 0)

                        nonce = profile_data.get('nonce', '')

                        current_boss = profile_data['currentBoss']
                        current_boss_level = current_boss['level']
                        boss_max_health = current_boss['maxHealth']
                        boss_current_health = current_boss['currentHealth']

                        spins = profile_data.get('spinEnergyTotal', 0)

                        logger.info(self.log_message(
                            f"Current boss level: <m>{current_boss_level}</m> | "
                            f"Boss health: <e>{boss_current_health}</e> out of <r>{boss_max_health}</r> | "
                            f"Balance: <c>{balance}</c> | Spins: <le>{spins}</le>"))

                        if settings.LINEA_WALLET is True:
                            linea_wallet = await self.wallet_check(http_client=http_client)
                            logger.info(self.log_message(f"💳 Linea wallet address: <y>{linea_wallet}</y>"))
                            if settings.LINEA_SHOW_BALANCE and linea_wallet != "-":
                                if settings.LINEA_API != '':
                                    balance_eth = await self.get_linea_wallet_balance(http_client=http_client,
                                                                                      linea_wallet=linea_wallet)
                                    eth_price = await self.get_eth_price(http_client=http_client,
                                                                         balance_eth=balance_eth)
                                    logger.info(self.log_message(f"ETH Balance: <g>{balance_eth}</g> | "
                                                                 f"USD Balance: <e>{eth_price}</e>"))
                                elif settings.LINEA_API == '':
                                    logger.info(self.log_message(f"💵 LINEA_API must be specified"
                                                                 f" to show the balance"))
                                    await asyncio.sleep(delay=3)

                        if boss_current_health == 0:
                            logger.info(self.log_message(f"👉 Setting next boss: <m>{current_boss_level + 1}</m> lvl"))
                            logger.info(self.log_message(f"😴 Sleep 10s"))
                            await asyncio.sleep(delay=10)

                            status = await self.set_next_boss(http_client=http_client)
                            if status is True:
                                logger.success(self.log_message(f"✅ Successful setting next boss: "
                                                                f"<m>{current_boss_level + 1}</m>"))

                        if settings.WATCH_VIDEO:
                            task_json = await self.get_campaigns(http_client=http_client)
                            n = 0
                            while n < 197:
                                campaigns_id = task_json[n]['id']
                                if task_json is not None:
                                    tasks_list = await self.get_tasks_list(http_client=http_client,
                                                                           campaigns_id=campaigns_id)
                                    if tasks_list:
                                        name = tasks_list[0]['name']
                                        status = tasks_list[0]['status']
                                        logger.info(self.log_message(f"Video: <r>{name}</r> | Status: <y>{status}</y>"))
                                        task_id = tasks_list[0]['id']
                                        await asyncio.sleep(delay=1)
                                        if status == 'Verification':
                                            logger.info(self.log_message(f"Unable to complete a task, it is already "
                                                                         f"in progress <lr>Skip video</lr>"))
                                            n += 1
                                            continue
                                        if tasks_list is not None and status != 'Verification':
                                            await asyncio.sleep(delay=2)
                                            verify_campaign = await self.verify_campaign(http_client=http_client,
                                                                                         task_id=task_id)
                                            status = verify_campaign['status']
                                            logger.info(self.log_message(f"Video: <r>{name}</r> | Status: "
                                                                         f"<y>{status}</y> Waiting 5s"))
                                            await asyncio.sleep(random.uniform(4, 6))
                                            if verify_campaign is not None:
                                                get_task_by_id = await self.get_task_by_id(http_client=http_client,
                                                                                           task_id=task_id)
                                                user_task_id = get_task_by_id['userTaskId']
                                                status = get_task_by_id['status']

                                                sleep_time_task = max((parser.isoparse(
                                                    get_task_by_id.get('verificationAvailableAt')) - datetime.now(
                                                    timezone.utc)).total_seconds() + 5, random.randint(5, 15))

                                                logger.info(self.log_message(f"Video: <r>{name}</r> | Status: "
                                                                             f"<y>{status}</y> Waiting {sleep_time_task}s"))
                                                await asyncio.sleep(delay=sleep_time_task)
                                                if get_task_by_id is not None:
                                                    complete_task = await self.complete_task(http_client=http_client,
                                                                                             user_task_id=user_task_id)
                                                    status = complete_task['status']
                                                    logger.info(self.log_message(f"Video: <r>{name}</r> | "
                                                                                 f"Status: <g>{status}</g>"))
                                                    await asyncio.sleep(delay=3)
                                                    n += 1

                    spins = profile_data.get('spinEnergyTotal', 0)
                    if settings.ROLL_CASINO:
                        while spins > settings.VALUE_SPIN:
                            await asyncio.sleep(delay=2)
                            play_data = await self.play_slotmachine(http_client=http_client)
                            reward_amount = play_data.get('spinResults', [{}])[0].get('rewardAmount', 0)
                            reward_type = play_data.get('spinResults', [{}])[0].get('rewardType', 'NO')
                            spins = play_data.get('gameConfig', {}).get('spinEnergyTotal', 0)
                            balance = play_data.get('gameConfig', {}).get('coinsAmount', 0)
                            if play_data.get('ethLotteryConfig', {}) is None:
                                eth_lottery_status = '-'
                                eth_lottery_ticket = '-'
                            else:
                                eth_lottery_status = play_data.get('ethLotteryConfig', {}).get('isCompleted', 0)
                                eth_lottery_ticket = play_data.get('ethLotteryConfig', {}).get('ticketNumber', 0)
                            logger.info(self.log_message(f"🎰 Casino game | Balance: <lc>{balance:,}</lc> "
                                                         f"(<lg>+{reward_amount:,}</lg> <lm>{reward_type}</lm>) | "
                                                         f"Spins: <le>{spins:,}</le> "))
                            if settings.LOTTERY_INFO:
                                logger.info(self.log_message(f"🎟 ETH Lottery status: {eth_lottery_status} | "
                                                             f"🎫 Ticket number: <ly>{eth_lottery_ticket}</ly>"))
                            await asyncio.sleep(delay=5)

                    taps = random.randint(a=settings.RANDOM_TAPS_COUNT[0], b=settings.RANDOM_TAPS_COUNT[1])
                    if taps > boss_current_health:
                        taps = boss_max_health - boss_current_health - 10
                        return taps
                    bot_config = await self.get_bot_config(http_client=http_client)
                    telegramMe = await self.get_telegram_me(http_client=http_client)

                    available_energy = profile_data['currentEnergy']
                    need_energy = taps * profile_data['weaponLevel']

                    # if first_check_clan():
                    #     clan = await self.get_clan(http_client=http_client)
                    #     set_first_run_check_clan()
                    #     await asyncio.sleep(1)
                    #     if clan is not False and clan != '71886d3b-1186-452d-8ac6-dcc5081ab204':
                    #         await asyncio.sleep(1)
                    #         clan_leave = await self.leave_clan(http_client=http_client)
                    #         if clan_leave is True:
                    #             await asyncio.sleep(1)
                    #             clan_join = await self.join_clan(http_client=http_client)
                    #             if clan_join is True:
                    #                 continue
                    #             elif clan_join is False:
                    #                 await asyncio.sleep(1)
                    #                 continue
                    #         elif clan_leave is False:
                    #             continue
                    #     elif clan == '71886d3b-1186-452d-8ac6-dcc5081ab204':
                    #         continue
                    #     else:
                    #         clan_join = await self.join_clan(http_client=http_client)
                    #         if clan_join is True:
                    #             continue
                    #         elif clan_join is False:
                    #             await asyncio.sleep(1)
                    #             continue

                    if telegramMe['isReferralInitialJoinBonusAvailable'] is True:
                        await self.claim_referral_bonus(http_client=http_client)
                        logger.info(self.log_message(f"🔥Referral bonus was claimed"))

                    if bot_config['isPurchased'] is False and settings.AUTO_BUY_TAPBOT is True:
                        await self.upgrade_boost(http_client=http_client, boost_type=UpgradableBoostType.TAPBOT)
                        logger.info(self.log_message(f"👉 Tapbot was purchased - 😴 Sleep 7s"))
                        await asyncio.sleep(delay=9)
                        bot_config = await self.get_bot_config(http_client=http_client)

                    if bot_config['isPurchased'] is True:
                        if bot_config['usedAttempts'] < bot_config['totalAttempts'] and not bot_config['endsAt']:
                            await self.start_bot(http_client=http_client)
                            bot_config = await self.get_bot_config(http_client=http_client)
                            logger.info(self.log_message(f"👉 Tapbot is started"))

                        else:
                            tapbotClaim = await self.claim_bot(http_client=http_client)
                            if tapbotClaim['isClaimed'] == False and tapbotClaim['data']:
                                logger.info(self.log_message(f"👉 Tapbot was claimed - 😴 Sleep 7s "
                                                             f"before starting again"))
                                await asyncio.sleep(delay=9)
                                bot_config = tapbotClaim['data']
                                await asyncio.sleep(delay=5)

                                if bot_config['usedAttempts'] < bot_config['totalAttempts']:
                                    await self.start_bot(http_client=http_client)
                                    logger.info(self.log_message(f"👉 Tapbot is started - 😴 Sleep 7s"))
                                    await asyncio.sleep(delay=9)
                                    bot_config = await self.get_bot_config(http_client=http_client)

                    if active_turbo:
                        taps += random.randint(a=settings.ADD_TAPS_ON_TURBO[0], b=settings.ADD_TAPS_ON_TURBO[1])
                        if taps > boss_current_health:
                            taps = boss_max_health - boss_current_health - 10
                            return taps

                        need_energy = 0

                        if time() - turbo_time > 10:
                            active_turbo = False
                            turbo_time = 0

                    if need_energy > available_energy or available_energy - need_energy < settings.MIN_AVAILABLE_ENERGY:
                        logger.warning(self.log_message(f"Need more energy ({available_energy}/{need_energy}, min:"
                                                        f" {settings.MIN_AVAILABLE_ENERGY}) for {taps} taps"))

                        sleep_between_clicks = random.randint(a=settings.SLEEP_BETWEEN_TAP[0],
                                                              b=settings.SLEEP_BETWEEN_TAP[1])
                        logger.info(self.log_message(f"Sleep {sleep_between_clicks}s"))
                        await asyncio.sleep(delay=sleep_between_clicks)
                        # update profile data
                        profile_data = await self.get_profile_data(http_client=http_client)
                        continue

                    profile_data = await self.send_taps(http_client=http_client, nonce=nonce, taps=taps)

                    if not profile_data:
                        continue

                    available_energy = profile_data['currentEnergy']
                    new_balance = profile_data['coinsAmount']

                    free_boosts = profile_data['freeBoosts']
                    turbo_boost_count = free_boosts['currentTurboAmount']
                    energy_boost_count = free_boosts['currentRefillEnergyAmount']

                    next_tap_level = profile_data['weaponLevel'] + 1
                    next_energy_level = profile_data['energyLimitLevel'] + 1
                    next_charge_level = profile_data['energyRechargeLevel'] + 1

                    nonce = profile_data['nonce']

                    current_boss = profile_data['currentBoss']
                    current_boss_level = current_boss['level']
                    boss_current_health = current_boss['currentHealth']

                    if boss_current_health <= 0:
                        logger.info(self.log_message(f"👉 Setting next boss: <m>{current_boss_level + 1}</m> lvl "
                                                     f"😴 Sleep 10s"))
                        await asyncio.sleep(delay=10)

                        status = await self.set_next_boss(http_client=http_client)
                        if status is True:
                            logger.success(self.log_message(f"✅ Successful setting next boss: "
                                                            f"<m>{current_boss_level + 1}</m>"))

                    taps_status = await self.send_taps(http_client=http_client, nonce=nonce, taps=taps)
                    taps_new_balance = taps_status['coinsAmount']
                    calc_taps = taps_new_balance - balance
                    if calc_taps > 0:
                        logger.success(self.log_message(
                            f"✅ Successful tapped! 🔨 | 👉 Current energy: {available_energy} "
                            f"| ⚡️ Minimum energy limit: {settings.MIN_AVAILABLE_ENERGY} | "
                            f"Balance: <c>{taps_new_balance}</c> (<g>+{calc_taps} 😊</g>) | "
                            f"Boss health: <e>{boss_current_health}</e>"))
                        balance = new_balance
                    else:
                        logger.info(self.log_message(
                            f"❌ Failed tapped! 🔨 | Balance: <c>{taps_new_balance}</c> "
                            f"(<g>No coin added 😥</g>) | 👉 Current energy: {available_energy} | "
                            f"⚡️ Minimum energy limit: {settings.MIN_AVAILABLE_ENERGY} | "
                            f"Boss health: <e>{boss_current_health}</e>"))
                        balance = new_balance
                        taps_status_json = json.dumps(taps_status)
                        logger.warning(self.log_message(f"❌ MemeFi server error 500"))
                        logger.info(self.log_message(f"😴 Sleep 10m"))
                        await asyncio.sleep(delay=600)
                        noBalance = True

                    if active_turbo is False:
                        if (energy_boost_count > 0
                                and available_energy < settings.MIN_AVAILABLE_ENERGY
                                and settings.APPLY_DAILY_ENERGY is True
                                and available_energy - need_energy < settings.MIN_AVAILABLE_ENERGY):
                            logger.info(self.log_message(f"😴 Sleep 7s before activating the daily energy boost"))
                            # await asyncio.sleep(delay=9)

                            status = await self.apply_boost(http_client=http_client, boost_type=FreeBoostType.ENERGY)
                            if status is True:
                                logger.success(self.log_message(f"👉 Energy boost applied"))

                                await asyncio.sleep(delay=3)

                            continue

                        if turbo_boost_count > 0 and settings.APPLY_DAILY_TURBO is True:
                            logger.info(self.log_message(f"😴 Sleep 10s before activating the daily turbo boost"))
                            await asyncio.sleep(delay=10)

                            status = await self.apply_boost(http_client=http_client, boost_type=FreeBoostType.TURBO)
                            if status is True:
                                logger.success(self.log_message(f"👉 Turbo boost applied"))

                                await asyncio.sleep(delay=9)

                                active_turbo = True
                                turbo_time = time()

                            continue

                        if settings.AUTO_UPGRADE_TAP is True and next_tap_level <= settings.MAX_TAP_LEVEL:
                            need_balance = 1000 * (2 ** (next_tap_level - 1))
                            if balance > need_balance:
                                status = await self.upgrade_boost(http_client=http_client,
                                                                  boost_type=UpgradableBoostType.TAP)
                                if status is True:
                                    logger.success(self.log_message(f"Tap upgraded to {next_tap_level} lvl"))

                                    await asyncio.sleep(delay=1)
                            else:
                                logger.info(self.log_message(f"Need more gold for upgrade tap to {next_tap_level} "
                                                             f"lvl ({balance}/{need_balance})"))

                        if settings.AUTO_UPGRADE_ENERGY is True and next_energy_level <= settings.MAX_ENERGY_LEVEL:
                            need_balance = 1000 * (2 ** (next_energy_level - 1))
                            if balance > need_balance:
                                status = await self.upgrade_boost(http_client=http_client,
                                                                  boost_type=UpgradableBoostType.ENERGY)
                                if status is True:
                                    logger.success(self.log_message(f"Energy upgraded to {next_energy_level} lvl"))

                                    await asyncio.sleep(delay=1)
                            else:
                                logger.warning(self.log_message(f"Need more gold for upgrade energy to "
                                                                f"{next_energy_level} lvl ({balance}/{need_balance})"))

                        if settings.AUTO_UPGRADE_CHARGE is True and next_charge_level <= settings.MAX_CHARGE_LEVEL:
                            need_balance = 1000 * (2 ** (next_charge_level - 1))

                            if balance > need_balance:
                                status = await self.upgrade_boost(http_client=http_client,
                                                                  boost_type=UpgradableBoostType.CHARGE)
                                if status is True:
                                    logger.success(self.log_message(f"\Charge upgraded to {next_charge_level} lvl"))

                                    await asyncio.sleep(delay=1)
                            else:
                                logger.warning(self.log_message(
                                    f"Need more gold for upgrade charge to {next_energy_level} "
                                    f"lvl ({balance}/{need_balance})"))

                        if available_energy < settings.MIN_AVAILABLE_ENERGY:
                            logger.info(self.log_message(f"👉 Minimum energy reached: {available_energy} | "
                                                         f"😴 Sleep {settings.SLEEP_BY_MIN_ENERGY}s"))
                            await asyncio.sleep(delay=settings.SLEEP_BY_MIN_ENERGY)

                            continue

                except InvalidSession as error:
                    raise error

                except InvalidProtocol:
                    raise

                except Exception as error:
                    log_error(self.log_message(f"❗️Unknown error: {error} | 😴 Wait 1h"))
                    await asyncio.sleep(delay=3600)

                else:
                    sleep_between_clicks = random.randint(a=settings.SLEEP_BETWEEN_TAP[0],
                                                          b=settings.SLEEP_BETWEEN_TAP[1])

                    if active_turbo is True:
                        sleep_between_clicks = 50
                    elif noBalance is True:
                        sleep_between_clicks = 700

                    logger.info(self.log_message(f"😴 Sleep {sleep_between_clicks}s"))
                    await asyncio.sleep(delay=sleep_between_clicks)


async def run_tapper(tg_client: TelegramClient):
    runner = Tapper(tg_client=tg_client)
    try:
        await runner.run()
    except InvalidSession as e:
        logger.error(runner.log_message(f"Invalid Session: {e}"))
    except InvalidProtocol as error:
        logger.error(f"{tg_client.name} | ❗️Invalid protocol detected at {error}")
