import os

def replace_in_file(filepath, old_text, new_text):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if old_text in content:
        content = content.replace(old_text, new_text)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")
    else:
        print(f"Could not find text in {filepath}")

# 1. config_fields.py
replace_in_file(
    r"backend\core\config_fields.py",
    '''    bhasha_batch_concurrency: int = Field(default=5, validation_alias="BHASHA_BATCH_CONCURRENCY")
    auto_remediation_dry_run: bool = Field(
        default=True, validation_alias="AUTO_REMEDIATION_DRY_RUN"
    )''',
    '''    bhasha_batch_concurrency: int = Field(default=5, validation_alias="BHASHA_BATCH_CONCURRENCY")'''
)

# 2. auth.py
auth_old_1 = '''oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"'''
auth_new_1 = '''oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ALGORITHM = "HS256"'''
replace_in_file(r"backend\api\routes\auth.py", auth_old_1, auth_new_1)

auth_old_2 = '''REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:'''
auth_new_2 = '''REFRESH_TOKEN_EXPIRE_DAYS = 7


def _get_secret_key() -> str:
    return settings.jwt_secret

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:'''
replace_in_file(r"backend\api\routes\auth.py", auth_old_2, auth_new_2)

replace_in_file(r"backend\api\routes\auth.py", "return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)", "return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)")

replace_in_file(r"backend\api\routes\auth.py", "payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])", "payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])")

replace_in_file(r"backend\api\routes\auth.py", '''        # বাংলা: type=access ছাড়া অন্য টোকেন (যেমন refresh) ব্যবহার রোধ।
        if payload.get("type") not in (None, "access"):''', '''        # বাংলা: type=access ছাড়া অন্য টোকেন (যেমন refresh) ব্যবহার রোধ।
        if payload.get("type") != "access":''')

replace_in_file(r"backend\api\routes\auth.py", '''    except Exception:
        logger.exception("Unhandled exception")
        return None''', '''    except (JWTError, ValueError):
        logger.debug("JWT decode failed in optional_current_user", exc_info=True)
        return None''')

replace_in_file(r"backend\api\routes\auth.py", "payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])", "payload = jwt.decode(body.refresh_token, _get_secret_key(), algorithms=[ALGORITHM])")

replace_in_file(r"backend\api\routes\auth.py", "await revoke_token(jti, exp=int(exp) if exp else None)", "await revoke_token(jti, exp=int(exp) if isinstance(exp, (int, float)) else None)")


# 3. security/__init__.py
sec_old_1 = '''            import asyncio
            import threading

            def check_revoked():'''
sec_new_1 = '''            import asyncio
            import threading
            from core.cache.redis_manager import redis_manager

            def check_revoked():'''
replace_in_file(r"backend\core\security\__init__.py", sec_old_1, sec_new_1)

sec_old_2 = '''                if loop and loop.is_running():
                    result = [False]

                    def run():
                        new_loop = asyncio.new_event_loop()
                        result[0] = new_loop.run_until_complete(is_token_revoked(jti))
                        new_loop.close()

                else:'''
sec_new_2 = '''                if loop and loop.is_running():
                    # Use run_coroutine_threadsafe to avoid cross-loop Redis errors
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(
                        is_token_revoked(jti), loop
                    )
                    try:
                        return future.result(timeout=5)
                    except (concurrent.futures.TimeoutError, Exception) as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Token revocation check timed out or failed: {e}")
                        return False
                else:'''
replace_in_file(r"backend\core\security\__init__.py", sec_old_2, sec_new_2)

sec_old_3 = '''        return payload
    except Exception as e:
        if type(e).__name__ == "ExpiredSignatureError":'''
sec_new_3 = '''        return payload
    except HTTPException:
        raise
    except Exception as e:
        if type(e).__name__ == "ExpiredSignatureError":'''
replace_in_file(r"backend\core\security\__init__.py", sec_old_3, sec_new_3)


# 4. middleware.py
replace_in_file(r"backend\api\middleware.py", "body_bytes = response.body if response.body else b\"{}\"", "body_bytes = response.body if response.body is not None else b\"{}\"")

# 5. factory.py
replace_in_file(r"backend\core\factory.py", "\"verified\": task_res.verification.verified,", "\"verified\": getattr(getattr(task_res, 'verification', None), 'verified', None),")

# 6. LivingDashboardShell.tsx
replace_in_file(r"frontend\src\components\dashboard\LivingDashboardShell.tsx", '''import { LiveSimulator } from './LiveSimulator';''', '''import type { ReactNode } from 'react';\nimport { LiveSimulator } from './LiveSimulator';''')

# 7. App.tsx
replace_in_file(r"frontend\src\App.tsx", '''import type { ChatMessage } from "./components/customer/UserDashboard";''', '''import type { ChatMessage } from "./services/chatService";''')

app_tsx_old = '''  const legacyWorkspace = (
    <UserDashboard
      customerMessages={chatMessages}
      customerInput={chatInput}
      setCustomerInput={setChatInput}
      loading={false}
      handleSendCustomer={handleSendCustomer}
      theme={theme}
      toggleTheme={toggleTheme}
      code={code}
      setCode={setCode}
      isServerOnline={isServerOnline}
      deployGate={deployGate}
      user={null}
      projects={[]}
      chatHistory={chatMessages}
      widgets={[]}
      onSaveToProject={handleSaveToProject}
      onPreview={handlePreview}
    />
  );'''
app_tsx_new = '''  const legacyWorkspace = (
    <UserDashboard />
  );'''
replace_in_file(r"frontend\src\App.tsx", app_tsx_old, app_tsx_new)

# 8. AIStudio.tsx
replace_in_file(r"frontend\src\pages\user\AIStudio.tsx", '''import type { ChatMessage } from '../../components/customer/UserDashboard';''', '''import type { ChatMessage } from '../../services/chatService';''')

# 9. UserDashboard.tsx
replace_in_file(r"frontend\src\components\customer\UserDashboard.tsx", '''import { Bot, Play, FolderOpen, Zap, MessageSquare, Plus, ArrowRight } from 'lucide-react';''', '''import { Bot, FolderOpen, Zap, MessageSquare, Plus, ArrowRight } from 'lucide-react';''')

# 10. heartbeat.ts
heartbeat_old = '''export const startAntiSleepHeartbeat = () => {
  setTimeout(() => { pingServers(); }, 10_000);
  setInterval(() => { pingServers(); }, 10 * 60 * 1000);
};'''
heartbeat_new = '''export const startAntiSleepHeartbeat = () => {
  const timeoutId = setTimeout(() => { pingServers(); }, 10_000);
  const intervalId = setInterval(() => { pingServers(); }, 10 * 60 * 1000);
  return { timeoutId, intervalId };
};'''
replace_in_file(r"frontend\src\services\heartbeat.ts", heartbeat_old, heartbeat_new)
