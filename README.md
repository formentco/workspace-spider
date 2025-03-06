# workspace-spider

Workspace Spider performs a discovery of key artefacts and information in the google environment

Currently it scans Confluence and Jira.

- **Github repository**: <https://github.com/formentco/workspace-spider/>


## Running the project

### 1. Setup dependencies
Your machine requires the following dependencies:

1. [Make](https://www.gnu.org/software/make/)
2. [UV](https://github.com/astral-sh/uv/releases)
 

### 2. Clone the repo

```bash
git clone https://github.com/formentco/workspace-spider.git
```


### 2. Set Up Your Environment

Then, install the environment and the pre-commit hooks with

```bash
make install
```

### 3. Atlassian

Obtain a API key from your profile in Atlassian

https://id.atlassian.com/manage-profile/security/api-tokens

You can use separate API tokens for different processes if you wish, however, each token has access to all products and all your access by default.

Once you are finished with the process: please remove the token from Atlassian! 

### 4. Env File

create an env file by copying the sample env to .env in the project root

```bash
cp sample_env .env
```

Update the 
CONFLUENCE_BASE_URL= with your subdomain
USERNAME= with the email address 
API_TOKEN=with your token for confluence
JIRA_BASE_URL= with your subdomain 
JIRA_API_TOKEN=with your token for JIRA
JIRA_USERNAME=with your email address


### 5. Run Confluence
If you wish to scan confluence, run the confluence command

```bash
make run-confluence
```

### 6. Run Jira
If you wish to scan jira, run the jira command

```bash
make run-jira
```