$root=Split-Path $PSScriptRoot -Parent
$proc=Start-Process -FilePath "$root/tools/jdk8u472-b08/bin/java.exe" -ArgumentList '-Xms128m','-Xmx768m','-jar',"$root/upstream/jshERP/jshERP-boot/target/jshERP.jar","--spring.config.additional-location=file:$($root.Replace('\','/'))/runtime/application.properties" -WorkingDirectory "$root/runtime" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$root/artifacts/backend-jdbc49.stdout.log" -RedirectStandardError "$root/artifacts/backend-jdbc49.stderr.log"
$proc.Id | Set-Content "$root/runtime/backend.pid"
