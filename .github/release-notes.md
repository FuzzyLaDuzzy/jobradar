JobRadar finds junior jobs and internships in your area of Portugal on many sites at once, keeps the ones that fit, scores each against your profile, and helps you apply and follow up. It runs on your own computer, or on your Android phone by itself.

## Install

**Android phone**: download **`JobRadar-…-android.apk`** below and open it. Android asks once to allow installs from your browser or Files. The app runs on the phone with no computer, and later versions install over it, keeping your keys, settings and jobs.

**Windows**: paste this line in PowerShell (Start menu → type "PowerShell"):

```powershell
irm https://raw.githubusercontent.com/FuzzyLaDuzzy/jobradar/main/install.ps1 | iex
```

**macOS / Linux** (with Python 3.10+):

```bash
curl -fsSL https://raw.githubusercontent.com/FuzzyLaDuzzy/jobradar/main/install.sh | sh
```

To update on a computer, run the same line again: your `config.yaml`, keys, jobs and backups are kept. The two installers are also below, to read before you run them.

On first start, the welcome screen asks for the keys (all optional: ITJobs, and Gemini for the free AI), and 👤 **Profile** reads your CV.

## What it does

- **Reads 19 kinds of sources**: company careers sites (SmartRecruiters, Workday, Lever, Greenhouse, Teamtailor, Workable…) and Portuguese job boards (ITJobs, Landing.jobs, Net-Empregos…), at the same time.
- **Keeps what fits**: your area, junior or internship level, your field; drops senior titles, scams and jobs that ask for years of experience. The ✂ **Cut** tab shows what was left out, and why.
- **Scores each job** against your profile, with keywords and, optionally, AI (Google Gemini, free, or Claude).
- **Helps you apply**: application message, interview prep, CV tailoring, and a follow-up email after 7 days with no reply.
- **Tracks your applications**: saved, applied, interview, offer, rejected, with notes, a summary and CSV export.
- Português / English, light and dark themes.

The APK is signed with the JobRadar key. Its certificate's SHA-256 is `E4:33:1B:3A:75:33:31:3F:2D:9C:DD:DF:46:A5:95:9C:0C:26:80:63:AD:DC:29:C8:DC:F9:29:1B:52:EE:D2:2C`.
