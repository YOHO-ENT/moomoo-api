# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities through GitHub Security Advisories:

https://github.com/YOHO-ENT/moomoo-api/security/advisories

If that channel is unavailable, contact the YOHO-ENT repository maintainers
through the GitHub repository.

Do not disclose sensitive information in public issues, pull requests, or
discussion threads. This includes trading passwords, account identifiers,
RSA private keys, OpenD configuration files, exported account data, and
debug logs.

## Sensitive Configuration

- Use `MOOMOO_TRADE_UNLOCK_PASSWORD` for examples that need a real-account
  trading unlock password.
- Use `MOOMOO_ALLOW_REAL_TRADING=1` only when you intentionally want an
  example to access a real trading account.
- Use `MOOMOO_INIT_RSA_FILE` or `SysConfig.set_init_rsa_file(...)` to point
  to your own RSA private key file when protocol encryption is enabled.
- Do not commit RSA private keys, `.pem` files, `.key` files, logs, account
  exports, or local OpenD configuration files.

Remote OpenD connections must use protocol encryption. Localhost development
connections may remain unencrypted if your local security posture allows it.
