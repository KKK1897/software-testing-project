$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:JAVA_HOME=Join-Path $root 'tools/jdk8u472-b08'
if (!(Test-Path "$root/artifacts/acceptance-junit.xml")) { throw '完整JUnit结果不存在，拒绝从未完成运行生成最终快照' }
& "$root/tools/allure-2.32.0/bin/allure.bat" generate "$root/artifacts/allure-acceptance" -o "$root/artifacts/allure-acceptance-report" --clean
if ($LASTEXITCODE -ne 0) { throw 'Allure报告生成失败' }
& "$root/tools/allure-2.32.0/bin/allure.bat" generate "$root/artifacts/allure-patch-regression" -o "$root/artifacts/allure-patch-report" --clean
if ($LASTEXITCODE -ne 0) { throw '补丁报告生成失败' }
