# Connecting Microsoft Teams

UniTask reads a student's Teams assignments through Microsoft Graph, on that student's behalf,
after they sign in on Microsoft's own page. It never sees their password and never writes to Teams.

## What it reads

| Permission (delegated) | Used for | Admin consent required by default? |
| --- | --- | --- |
| `EduAssignments.ReadBasic` | `GET /education/me/assignments?$expand=submissions`: title, due date, points, turned-in status | No |
| `EduRoster.ReadBasic` | `GET /education/me/classes`: class names | No |
| `User.Read` | Who connected (shown as "Connected as …") | No |
| `offline_access` (added automatically) | A refresh token so UniTask can keep syncing every 30 minutes | No |

"No" is Microsoft's default. **A college can still switch off user consent for third-party apps.** In that
case Microsoft shows "Need admin approval" and UniTask records the connection as *needs consent*,
with a message telling the student what to ask IT for. UniTask does not try to get around that.

## 1. Register the app in Microsoft Entra (about 5 minutes)

You need a Microsoft Entra tenant you can create app registrations in.

- **Try your college account first.** Many universities leave "Users can register applications" on.
  Go to <https://entra.microsoft.com> → *Applications* → *App registrations* → *New registration*.
  If you get "You do not have access", that route is closed. Use the next option.
- **Otherwise use your own tenant.** A free Azure account creates one. The app can still be used by
  students from any college because it's registered as multi-tenant.

New registration:

1. **Name:** `UniTask`
2. **Supported account types:** *Accounts in any organizational directory (Any Microsoft Entra ID tenant – Multitenant)*
3. **Redirect URI:** platform **Web**, value `http://localhost:5173/api/integrations/teams/callback`
4. Register. Copy the **Application (client) ID**.
5. *Certificates & secrets* → *New client secret* → copy the **Value** (shown once).
6. *API permissions* → *Add a permission* → *Microsoft Graph* → *Delegated* → add
   `EduAssignments.ReadBasic`, `EduRoster.ReadBasic`, `User.Read`. (Leave "Grant admin consent" alone
   unless you are an admin of the tenant your students are in.)

## 2. Configure the backend

In `backend/.env` (never commit this file):

```dotenv
MS_CLIENT_ID=<Application (client) ID>
MS_CLIENT_SECRET=<client secret value>
MS_TENANT=organizations
FRONTEND_URL=http://localhost:5173
TEAMS_AUTO_SYNC_MINUTES=30
```

Restart the backend. Sign in to UniTask as a **student** → *Teams sync* → **Connect Microsoft Teams**.

## 3. What happens after connecting

1. Microsoft redirects back to `/api/integrations/teams/callback` (as a form POST).
2. The backend exchanges the code (with PKCE), encrypts the MSAL token cache, and runs the first sync.
3. Classes appear under *Classes → From Microsoft Teams*. Assignments appear in *Today* and *Deadlines*.
   The first sync imports quietly, so it doesn't flood the student with "new" notifications.
4. Every `TEAMS_AUTO_SYNC_MINUTES` the server syncs again for every connected student. Each sync detects:
   - **new assignments**, shown under *What changed since you last looked*
   - **moved due dates**: old date struck through, new date shown. Moved earlier ranks higher.
   - **renamed** and **removed** assignments
   - **turned in on Teams**: the item drops off the to-do list
5. Students can't mark a Teams item done inside UniTask. Teams stays the source of truth.

## Troubleshooting

| What you see | Cause | Fix |
| --- | --- | --- |
| "Teams sync isn't set up on this server yet" | `MS_CLIENT_ID`/`MS_CLIENT_SECRET` missing | Fill `backend/.env`, restart |
| Microsoft page: *Need admin approval* | College blocks user consent | IT admin must grant consent for the app (the message in UniTask says exactly which permissions) |
| `AADSTS50011` redirect URI mismatch | Redirect URI in Entra ≠ `MS_REDIRECT_URI` | Make them identical, including port |
| `AADSTS700016` application not found | Wrong client ID, or app not multi-tenant | Check step 1.2 |
| Connected, 0 assignments | Account isn't a student in any Teams *class* team, or the college doesn't use Teams Assignments | Expected. Only class teams with Assignments have data |
| "Microsoft refused access…" after connecting | Graph returned 403 for `/education` | Same as admin approval, or Education features not licensed |
