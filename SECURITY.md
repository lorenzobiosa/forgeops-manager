# 🔐 Security Policy

## Reporting a Vulnerability

Thank you for helping us keep this project secure! 🛡️

If you discover a potential security issue, please **do not create a public issue**. Instead, report it privately via:

- Email: `lorenzo@biosa-labs.com`
- GPG encryption recommended for sensitive information: use our public key at `https://github.com/lorenzobiosa/lorenzobiosa/blob/master/keys/gpg-publickey.asc`

Please include:

1. **Detailed description** of the vulnerability
2. **Steps to reproduce** or a proof-of-concept
3. **Impact assessment** (optional, if known)
4. **Environment details** (OS, versions, configuration)

We aim to respond within **3 business days**.

---

## 🛠 Supported Versions

- **Main / Latest Release**: Actively maintained and patched
- **Previous LTS Releases**: Security patches only
- **Unsupported Releases**: No security updates

Always use the **latest supported version** for production environments.

---

## 🕒 Response and Patch Timeline

- Acknowledgement: Within **3 business days**
- Initial assessment: Within **7 days**
- Patch release: **ASAP**, prioritizing high-risk vulnerabilities
- Communication: Public disclosure coordinated after a fix is released

---

## 📝 Guidelines for Contributors

- Do **not commit secrets** (API keys, passwords, certificates)
- Check `.gitignore` for sensitive files
- Use GitHub Actions / CI for automated secret scanning
- Follow our `SECURITY.md` and `CODE_OF_CONDUCT.md` during all interactions

---

## 💡 Responsible Disclosure

We follow **responsible disclosure practices**:

- You report it privately
- We verify, fix, and release a patch
- Then we publicly announce the vulnerability and fix

We respect and credit security researchers who follow these guidelines.

---

## 🔗 Additional Resources

- [GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Responsible Disclosure Guide](https://www.owasp.org/index.php/OWASP_Responsible_Disclosure_Guideline)
