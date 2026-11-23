
<p align="center">
  <img src="https://i.supaimg.com/af2484ff-b3c4-4b44-8b12-dbd98b1bdd57/066c67c0-ca3f-45f0-bd94-38ffb9c65c9d.jpg" alt="Spotify Checker" width="200"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-1DB954?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Status-Active-1DB954?style=for-the-badge"/>
</p>

<p align="center">
  <img src="https://i.supaimg.com/af2484ff-b3c4-4b44-8b12-dbd98b1bdd57/1633d153-8061-48ba-8620-7071788a01ec.jpg" alt="Spotify Icon" width="20" style="vertical-align: middle; border-radius: 50%; margin-right: 5px;"/>
  <b>Spotify account checker powered by <code>sp_dc</code> cookies</b><br/>
  <i>Automatic login · Account data extraction · Hijack detection · Organized export</i>
</p>

---

## What it does

It takes Spotify `sp_dc` authentication cookies — whether submitted as text or extracted from uploaded files/archives — and uses them to log into those accounts without a password, pull each account's email, username, plan, and renewal date, and check whether the account's email can be changed without a password (i.e., whether the account can be hijacked). For a batch of cookies, it packages the results into a zip file sorted into 'hijackable,' 'not hijackable,' and 'dead' folders.

> **Legal Notice:** This tool is intended for **educational and security research purposes only**. Using it on accounts you do not own violates the law and Spotify's Terms of Service. The user bears full responsibility.

---

## Run

Start the script using the following command:

```bash
python3 spotify.py
