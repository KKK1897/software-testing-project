$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:JAVA_HOME=Join-Path $root 'tools/jdk8u472-b08'
$boot=Join-Path $root 'upstream/jshERP/jshERP-boot'
$original=Get-Content (Join-Path $boot 'pom.xml') -Raw
# 独立构建描述符：仅替换旧 JDBC 驱动，保持原始受测业务源码。
$adjusted=$original.Replace('<version>5.1.30</version>','<version>5.1.49</version>')
if ($adjusted -eq $original) { throw '固定版本 POM 与预期不同' }
Set-Content (Join-Path $boot 'pom.qa.xml') $adjusted -Encoding utf8
& "$root/tools/apache-maven-3.6.3/bin/mvn.cmd" -B -s "$PSScriptRoot/maven-settings.xml" -f "$boot/pom.qa.xml" "-Dmaven.repo.local=$root/tools/m2" -DskipTests package
if ($LASTEXITCODE -ne 0) { throw '后端构建失败' }
