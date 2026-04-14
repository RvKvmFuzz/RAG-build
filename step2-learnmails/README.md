# AI Learning Script for KVM-RISCV Mail List

This script uses AI to process KVM-RISCV bug fix emails from a mailing list and generates structured learning documents. It extracts key bug-related information from the email threads, such as bug type, trigger, fix, learned experiences, and stores them in a knowledge base for further analysis.

## Requirements

Before running this script, make sure you have the following installed and set up:

* Python 3.x
* Required Python libraries (see `requirements.txt`)
* Access to the RAGFlow API and LLM API
* API keys for both RAGFlow and LLM (you can specify them via environment variables or a key file)

## Setup

1. **Install dependencies** :
   Ensure that the required libraries are installed by running:

```bash
   pip install -r requirements.txt
```

1. **Environment Variables** :
   You must set the following environment variables for the script to function:

* `RAGFLOW_API_URL`: The URL for RAGFlow API.
* `RAGFLOW_API_KEY`: The API key for RAGFlow.
* `LLM_API_URL`: The URL for the LLM API.
* `LLM_API_KEY`: The API key for the LLM service.

1. **API Key File for LLM** :
   Create a file named `llm_api.key` in the script's parent directory. The file should contain your LLM API key.
2. **Bug Types** :
   The script includes predefined bug types. Ensure that you understand these types as they will be used for classification when processing the emails.

## Usage

The script processes a given dataset from the KVM-RISCV mailing list and generates structured bug-fix knowledge. You can either create a new knowledge base or use an existing one.

### Command-line Arguments

* `<source_dataset_id>`: The source knowledge base ID (KVM-RISCV mailing list).
* `--limit <n>`: Limit the number of documents to process. Default is 2 (for testing).
* `--start <index>`: Start index for processing documents. Default is 0.
* `--create-dataset`: Option to create a new knowledge base.

### Example Usage

1. **Run the script with existing knowledge base** :

```bash
   python3 ai_learn_from_mails.py <source_dataset_id> --limit 5
```

1. **Create a new knowledge base** :

```bash
   python3 ai_learn_from_mails.py <source_dataset_id> --create-dataset
```

1. **Process a specific range of documents** :

```bash
   python3 ai_learn_from_mails.py <source_dataset_id> --limit 10 --start 10
```

## Script Workflow

1. **Step 1: Create or Get Target Knowledge Base** :
   The script either creates a new knowledge base or searches for an existing one.
2. **Step 2: List Documents** :
   It retrieves a list of documents from the source knowledge base (KVM-RISCV mail list).
3. **Step 3: Process Documents** :
   For each document, it fetches the email content and uses a Large Language Model (LLM) to extract the following information:

* **BUG_TYPE** : The type of bug (e.g., memory leak, race condition).
* **BUG_TRIGGER** : A brief description of how the bug is triggered.
* **PATCH_FIX** : A brief description of how the patch fixes the bug.
* **LEARNED_EXPERIENCES** : A list of lessons learned, including code writing standards, commit message guidelines, and reviewer suggestions.
* **MAIL_ID** : The unique identifier of the email.

  The extracted information is saved as structured documents and uploaded to the target knowledge base.

1. **Step 4: Trigger Parsing** :
   Once the new document is uploaded, the script triggers the parsing process in the target knowledge base.

## Output

The learning content for each processed email will be saved in the specified output directory (default is `/root/.openclaw/workspace/learn-kvm-riscv-output`). The documents are also uploaded to the target knowledge base for further processing and analysis.

### Sample Output Format

For each email, the output will look like this:

```
BUG_TYPE:
<Selected Bug Type>

BUG_TRIGGER:
<One-sentence description of the bug trigger>

PATCH_FIX:
<One-sentence description of how the patch fixes the bug>

LEARNED_EXPERIENCES:
- [Tag] Experience content 1
- [Tag] Experience content 2
- [Tag] Experience content 3
...

MAIL_ID:
<Source document ID>
```

## Troubleshooting

1. **Missing Content** :
   If the script cannot fetch the email content, it will skip that document and continue processing.
2. **API Key Issues** :
   Make sure that the API keys are correctly set up and accessible by the script.
3. **Connection Errors** :
   Network issues may cause connection problems. Ensure that your internet connection is stable and retry.
