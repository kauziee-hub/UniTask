"""Amazon Cognito user-pool accounts (AUTH_PROVIDER=cognito).

The app client must be a public client (no secret) with USER_PASSWORD_AUTH enabled.
Credentials for the Cognito API come from the normal AWS credential chain; sign-up
and sign-in are unauthenticated Cognito operations, so no IAM permissions are needed
for them.
"""

import logging
import os
from functools import lru_cache

import jwt

logger = logging.getLogger(__name__)


class CognitoError(RuntimeError):
    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


def _settings() -> tuple[str, str, str]:
    region = os.getenv("COGNITO_REGION") or os.getenv("AWS_REGION", "ap-south-1")
    pool_id = os.getenv("COGNITO_USER_POOL_ID", "")
    client_id = os.getenv("COGNITO_APP_CLIENT_ID", "")
    if not pool_id or not client_id:
        raise CognitoError("Cognito is selected but COGNITO_USER_POOL_ID / COGNITO_APP_CLIENT_ID are not set.")
    return region, pool_id, client_id


@lru_cache
def _client():
    import boto3

    region, _, _ = _settings()
    profile = os.getenv("AWS_PROFILE") or None
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.client("cognito-idp", region_name=region)


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    region, pool_id, _ = _settings()
    return jwt.PyJWKClient(f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json")


def _call(operation: str, **kwargs) -> dict:
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        return getattr(_client(), operation)(**kwargs)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        raise CognitoError(error.get("Message", "Cognito rejected the request."), error.get("Code", "")) from exc
    except BotoCoreError as exc:
        logger.exception("Cognito request failed.")
        raise CognitoError("Could not reach Amazon Cognito.") from exc


def sign_up(email: str, password: str, name: str) -> str:
    _, _, client_id = _settings()
    response = _call(
        "sign_up",
        ClientId=client_id,
        Username=email,
        Password=password,
        UserAttributes=[{"Name": "email", "Value": email}, {"Name": "name", "Value": name}],
    )
    return response["UserSub"]


def confirm_sign_up(email: str, code: str) -> None:
    _, _, client_id = _settings()
    _call("confirm_sign_up", ClientId=client_id, Username=email, ConfirmationCode=code)


def sign_in(email: str, password: str) -> str:
    _, _, client_id = _settings()
    response = _call(
        "initiate_auth",
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    result = response.get("AuthenticationResult")
    if not result:
        raise CognitoError("Additional sign-in steps are required for this account.", "ChallengeRequired")
    return result["IdToken"]


def verify_id_token(token: str, jwks_client: jwt.PyJWKClient | None = None) -> dict | None:
    region, pool_id, client_id = _settings()
    try:
        signing_key = (jwks_client or _jwks_client()).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=f"https://cognito-idp.{region}.amazonaws.com/{pool_id}",
        )
    except jwt.PyJWTError:
        return None
    if claims.get("token_use") != "id":
        return None
    return claims
