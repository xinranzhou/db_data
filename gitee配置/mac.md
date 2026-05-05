Add new self-hosted runner · xinranzhou/db_data
Using self-hosted runners in public repositories is not recommended. Forks of your public repository can potentially run dangerous code on your self-hosted runner by creating a pull request. Learn more about security hardening for self-hosted runners.

Adding a self-hosted runner requires that you download, configure, and execute the GitHub Actions Runner. If you do not already have an existing volume licensing agreement for your GitHub purchases, by downloading and configuring the GitHub Actions Runner, you agree to the GitHub Customer Agreement.

Runner image

macOS

Linux

Windows
Architecture
Download
# Create a folder
$ mkdir actions-runner && cd actions-runner# Download the latest runner package
$ curl -o actions-runner-osx-x64-2.334.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.334.0/actions-runner-osx-x64-2.334.0.tar.gz# Optional: Validate the hash
$ echo "73a979ff7e9ce8a70244f3a959d896870be486fac92bb08ed90684f961474e0d  actions-runner-osx-x64-2.334.0.tar.gz" | shasum -a 256 -c# Extract the installer
$ tar xzf ./actions-runner-osx-x64-2.334.0.tar.gz
Configure
# Create the runner and start the configuration experience
$ ./config.sh --url https://github.com/xinranzhou/db_data --token AB7OX2O3LNSHM265XNWGTJTJ7HZSO# Last step, run it!
$ ./run.sh
Using your self-hosted runner
# Use this YAML in your workflow file for each job
runs-on: self-hosted


-----


Add new self-hosted runner · xinranzhou/db_data
Using self-hosted runners in public repositories is not recommended. Forks of your public repository can potentially run dangerous code on your self-hosted runner by creating a pull request. Learn more about security hardening for self-hosted runners.

Adding a self-hosted runner requires that you download, configure, and execute the GitHub Actions Runner. If you do not already have an existing volume licensing agreement for your GitHub purchases, by downloading and configuring the GitHub Actions Runner, you agree to the GitHub Customer Agreement.

Runner image

macOS

Linux

Windows
Architecture
Download
# Create a folder
$ mkdir actions-runner && cd actions-runner# Download the latest runner package
$ curl -o actions-runner-linux-x64-2.334.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.334.0/actions-runner-linux-x64-2.334.0.tar.gz# Optional: Validate the hash
$ echo "048024cd2c848eb6f14d5646d56c13a4def2ae7ee3ad12122bee960c56f3d271  actions-runner-linux-x64-2.334.0.tar.gz" | shasum -a 256 -c# Extract the installer
$ tar xzf ./actions-runner-linux-x64-2.334.0.tar.gz
Configure
# Create the runner and start the configuration experience
$ ./config.sh --url https://github.com/xinranzhou/db_data --token AB7OX2O3LNSHM265XNWGTJTJ7HZSO# Last step, run it!
$ ./run.sh
Using your self-hosted runner
# Use this YAML in your workflow file for each job
runs-on: self-hosted
For additional details about configuring, running, or shutting down the runner, please check out our product docs.


---
Add new self-hosted runner · xinranzhou/db_data
Using self-hosted runners in public repositories is not recommended. Forks of your public repository can potentially run dangerous code on your self-hosted runner by creating a pull request. Learn more about security hardening for self-hosted runners.

Adding a self-hosted runner requires that you download, configure, and execute the GitHub Actions Runner. If you do not already have an existing volume licensing agreement for your GitHub purchases, by downloading and configuring the GitHub Actions Runner, you agree to the GitHub Customer Agreement.

Runner image

macOS

Linux

Windows
Architecture
Download
We recommend configuring the runner under "\actions-runner". This will help avoid issues related to service identity folder permissions and long path restrictions on Windows.

# Create a folder under the drive root
$ mkdir actions-runner; cd actions-runner# Download the latest runner package
$ Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.334.0/actions-runner-win-x64-2.334.0.zip -OutFile actions-runner-win-x64-2.334.0.zip# Optional: Validate the hash
$ if((Get-FileHash -Path actions-runner-win-x64-2.334.0.zip -Algorithm SHA256).Hash.ToUpper() -ne 'a0c896f3acf37841cc17f392a38111d39501e56f2990434567f027ee89cf8981'.ToUpper()){ throw 'Computed checksum did not match' }# Extract the installer
$ Add-Type -AssemblyName System.IO.Compression.FileSystem ; [System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD/actions-runner-win-x64-2.334.0.zip", "$PWD")
Configure
# Create the runner and start the configuration experience
$ ./config.cmd --url https://github.com/xinranzhou/db_data --token AB7OX2O3LNSHM265XNWGTJTJ7HZSO# Run it!
$ ./run.cmd
Using your self-hosted runner
# Use this YAML in your workflow file for each job
runs-on: self-hosted
For additional details about configuring, running, or shutting dow

报错：
(Line: 116, Col: 16): Unrecognized named-value: 'runner'. Located at position 1 within expression: runner.os == 'Windows' && 'pwsh' || 'bash', (Line: 121, Col: 16): Unrecognized named-value: 'runner'. Located at position 1 within expression: runner.os == 'Windows' && 'pwsh' || 'bash', (Line: 128, Col: 16): Unrecognized named-value: 'runner'. Located at position 1 within expression: runner.os == 'Windows' && 'pwsh' || 'bash', (Line: 141, Col: 16): Unrecognized named-value: 'runner'. Located at position 1 within expression: runner.os == 'Windows' && 'pwsh' || 'bash'


