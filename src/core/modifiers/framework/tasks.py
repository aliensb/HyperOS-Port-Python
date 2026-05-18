"""Specific framework modification tasks."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.modifiers.framework.base import FrameworkModifierBase
from src.core.modifiers.framework.patches import (
    INVOKE_TRUE,
    MY_PLATFORM_KEY,
    RETRUN_FALSE,
    RETRUN_TRUE,
)

if TYPE_CHECKING:
    from src.core.context import PortingContext


class FrameworkTasks(FrameworkModifierBase):
    """Specific modification tasks for framework-level changes."""

    def __init__(self, context: PortingContext) -> None:
        super().__init__(context)

    def _mod_miui_services(self) -> None:
        """Modify miui-services.jar for EU ROM compatibility."""
        jar_path = self._find_file(self.ctx.target_dir, "miui-services.jar")
        if not jar_path:
            return

        # Check cache first
        cached_jar = self._get_cached_jar("miui-services.jar")
        if cached_jar:
            self.logger.info("Using cached modified miui-services.jar")
            shutil.copy2(cached_jar, jar_path)
            return

        self.logger.info(f"Modifying {jar_path.name}...")
        work_dir = self.temp_dir / "miui-services"
        self._apkeditor_decode(jar_path, work_dir)

        if getattr(self.ctx, "is_port_eu_rom", False):
            fuc_body = ".locals 1\n    invoke-direct {p0}, Lcom/android/server/SystemServerStub;-><init>()V\n    return-void"
            self._run_smalikit(
                path=str(work_dir),
                iname="SystemServerImpl.smali",
                method="<init>()V",
                remake=fuc_body,
            )

        remake_void = ".locals 0\n    return-void"
        remake_false = ".locals 1\n    const/4 v0, 0x0\n    return v0"

        self._run_smalikit(
            path=str(work_dir),
            iname="PackageManagerServiceImpl.smali",
            method="verifyIsolationViolation",
            remake=remake_void,
            recursive=True,
        )
        self._run_smalikit(
            path=str(work_dir),
            iname="PackageManagerServiceImpl.smali",
            method="canBeUpdate",
            remake=remake_void,
            recursive=True,
        )

        patches = [
            (
                "com/android/server/am/BroadcastQueueModernStubImpl.smali",
                [("sget-boolean v2, Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z", "const/4 v2, 0x1")],
            ),
            (
                "com/android/server/am/ActivityManagerServiceImpl.smali",
                [
                    (
                        "sget-boolean v1, Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z",
                        "const/4 v1, 0x1",
                    ),
                    (
                        "sget-boolean v4, Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z",
                        "const/4 v4, 0x1",
                    ),
                ],
            ),
            (
                "com/android/server/am/ProcessManagerService.smali",
                [("sget-boolean v0, Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z", "const/4 v0, 0x1")],
            ),
            (
                "com/android/server/am/ProcessSceneCleaner.smali",
                [("sget-boolean v4, Lmiui/os/Build;->IS_INTERNATIONAL_BUILD:Z", "const/4 v0, 0x1")],
            ),
        ]

        for rel_path, rules in patches:
            target_smali = self._find_file(work_dir, Path(rel_path).name)
            if target_smali:
                for old_str, new_str in rules:
                    self._replace_text_in_file(target_smali, old_str, new_str)

        self._run_smalikit(
            path=str(work_dir),
            iname="WindowManagerServiceImpl.smali",
            method="notAllowCaptureDisplay(Lcom/android/server/wm/RootWindowContainer;I)Z",
            remake=remake_false,
            recursive=True,
        )

        self._apkeditor_build(work_dir, jar_path)

        # Save to cache
        self._save_jar_cache("miui-services.jar", jar_path)

    def _mod_services(self) -> None:
        """Modify services.jar for signature and package verification bypass."""
        jar_path = self._find_file(self.ctx.target_dir, "services.jar")
        if not jar_path:
            return

        # Check cache first
        cached_jar = self._get_cached_jar("services.jar")
        if cached_jar:
            self.logger.info("Using cached modified services.jar")
            shutil.copy2(cached_jar, jar_path)
            return

        self.logger.info(f"Modifying {jar_path.name}...")
        work_dir = self.temp_dir / "services"
        shutil.copy2(jar_path, self.temp_dir / "services.jar.bak")
        self._apkeditor_decode(jar_path, work_dir)

        remake_void = ".locals 0\n    return-void"
        remake_false = ".locals 1\n    const/4 v0, 0x0\n    return v0"
        remake_true = ".locals 1\n    const/4 v0, 0x1\n    return v0"

        self._run_smalikit(
            path=str(work_dir),
            iname="PackageManagerServiceUtils.smali",
            method="checkDowngrade",
            remake=remake_void,
            recursive=True,
        )
        for m in [
            "matchSignaturesCompat",
            "matchSignaturesRecover",
            "matchSignatureInSystem",
            "verifySignatures",
        ]:
            self._run_smalikit(
                path=str(work_dir),
                iname="PackageManagerServiceUtils.smali",
                method=m,
                remake=remake_false,
            )

        self._run_smalikit(
            path=str(work_dir),
            iname="KeySetManagerService.smali",
            method="checkUpgradeKeySetLocked",
            remake=remake_true,
        )

        self._run_smalikit(
            path=str(work_dir),
            iname="VerifyingSession.smali",
            method="isVerificationEnabled",
            remake=remake_false,
        )

        self._apkeditor_build(work_dir, jar_path)

        # Save to cache
        self._save_jar_cache("services.jar", jar_path)

    def _mod_framework(self) -> None:
        """Modify framework.jar for signature bypass and PropsHook."""
        jar = self._find_file(self.ctx.target_dir, "framework.jar")
        if not jar:
            return

        self.logger.info(f"Modifying {jar.name} (PropsHook & SignBypass)...")

        wd = self.temp_dir / "framework"
        self.shell.run_java_jar(
            self.apkeditor_path, ["d", "-f", "-i", str(jar), "-o", str(wd), "-no-dex-debug"]
        )

        # Inject PropsHook
        props_hook_zip = Path("devices/common/PropsHook.zip")
        if props_hook_zip.exists():
            self.logger.info("Injecting PropsHook...")
            hook_tmp = self.temp_dir / "PropsHook"
            with zipfile.ZipFile(props_hook_zip, "r") as z:
                z.extractall(hook_tmp)

            classes_dex = hook_tmp / "classes.dex"
            if classes_dex.exists():
                classes_out = hook_tmp / "classes"
                self.shell.run_java_jar(
                    self.baksmali_path, ["d", str(classes_dex), "-o", str(classes_out)]
                )
                self._copy_to_next_classes(wd, classes_out)

        self.logger.info("Applying Signature Bypass Patches...")

        self._run_smalikit(
            path=str(wd),
            iname="StrictJarVerifier.smali",
            method="verifyMessageDigest([B[B)Z",
            remake=RETRUN_TRUE,
        )
        self._run_smalikit(
            path=str(wd),
            iname="StrictJarVerifier.smali",
            method="<init>(Ljava/lang/String;Landroid/util/jar/StrictJarManifest;Ljava/util/HashMap;Z)V",
            before_line=[
                "iput-boolean p4, p0, Landroid/util/jar/StrictJarVerifier;->signatureSchemeRollbackProtectionsEnforced:Z",
                "const/4 p4, 0x0",
            ],
        )

        targets = [
            ("ApkSigningBlockUtils.smali", "verifyIntegrityFor1MbChunkBasedAlgorithm"),
            ("ApkSigningBlockUtils.smali", "verifyProofOfRotationStruct"),
            ("ApkSignatureSchemeV2Verifier.smali", "verifySigner"),
            ("ApkSignatureSchemeV3Verifier.smali", "verifySigner"),
            ("ApkSignatureSchemeV4Verifier.smali", "verifySigner"),
        ]
        s1 = "Ljava/security/MessageDigest;->isEqual([B[B)Z"
        s2 = "Ljava/security/Signature;->verify([B)Z"

        for smali_file, method in targets:
            self._run_smalikit(
                path=str(wd),
                iname=smali_file,
                method=method,
                after_line=[s1, INVOKE_TRUE],
                recursive=True,
            )
            self._run_smalikit(
                path=str(wd),
                iname=smali_file,
                method=method,
                after_line=[s2, INVOKE_TRUE],
                recursive=True,
            )

        for m in [
            "checkCapability",
            "checkCapabilityRecover",
            "hasCommonAncestor",
            "signaturesMatchExactly",
        ]:
            self._run_smalikit(
                path=str(wd),
                iname="PackageParser$SigningDetails.smali",
                method=m,
                remake=RETRUN_TRUE,
                recursive=True,
            )
            self._run_smalikit(
                path=str(wd),
                iname="SigningDetails.smali",
                method=m,
                remake=RETRUN_TRUE,
                recursive=True,
            )

        self._run_smalikit(
            path=str(wd),
            iname="AssetManager.smali",
            method="containsAllocatedTable",
            remake=RETRUN_FALSE,
        )

        self._run_smalikit(
            path=str(wd),
            iname="StrictJarFile.smali",
            method="<init>(Ljava/lang/String;Ljava/io/FileDescriptor;ZZ)V",
            after_line=["move-result-object v6", "const/4 v6, 0x1"],
        )

        self._run_smalikit(
            path=str(wd),
            iname="ApkSignatureVerifier.smali",
            method="getMinimumSignatureSchemeVersionForTargetSdk",
            remake=RETRUN_TRUE,
        )

        # Hook Instrumentation for PropsHook
        inst_smali = self._find_file(wd, "Instrumentation.smali")
        if inst_smali:
            content = inst_smali.read_text(encoding="utf-8", errors="ignore")

            method1 = "newApplication(Ljava/lang/ClassLoader;Ljava/lang/String;Landroid/content/Context;)Landroid/app/Application;"
            if method1 in content:
                reg = self._extract_register_from_invoke(
                    content,
                    method1,
                    "Landroid/app/Application;->attach(Landroid/content/Context;)V",
                    arg_index=1,
                )
                if reg:
                    patch_code = f"    invoke-static {{{reg}}}, Lcom/android/internal/util/PropsHookUtils;->setProps(Landroid/content/Context;)V"
                    self._run_smalikit(
                        file_path=str(inst_smali),
                        method=method1,
                        before_line=["return-object", patch_code],
                    )

            method2 = "newApplication(Ljava/lang/Class;Landroid/content/Context;)Landroid/app/Application;"
            if method2 in content:
                reg = self._extract_register_from_invoke(
                    content,
                    method2,
                    "Landroid/app/Application;->attach(Landroid/content/Context;)V",
                    arg_index=1,
                )
                if reg:
                    patch_code = f"    invoke-static {{{reg}}}, Lcom/android/internal/util/PropsHookUtils;->setProps(Landroid/content/Context;)V"
                    self._run_smalikit(
                        file_path=str(inst_smali),
                        method=method2,
                        before_line=["return-object", patch_code],
                    )

        # Hook ApplicationPackageManager
        app_pm_smali = self._find_file(wd, "ApplicationPackageManager.smali")
        if app_pm_smali:
            method_sig = "hasSystemFeature(Ljava/lang/String;I)Z"
            repl_pattern = (
                r"invoke-static {p1, \1}, Lcom/android/internal/util/PropsHookUtils;->hasSystemFeature(Ljava/lang/String;Z)Z"
                r"\n    move-result \1"
                r"\n    return \1"
            )
            self._run_smalikit(
                file_path=str(app_pm_smali),
                method=method_sig,
                regex_replace=(r"return\s+([vp]\d+)", repl_pattern),
            )

        # Hook PendingIntent for AutoCopy
        target_file = self._find_file(wd, "PendingIntent.smali")
        if target_file:
            hook_code = "\n    # [AutoCopy Hook]\n    invoke-static {p0, p2}, Lcom/android/internal/util/HookHelper;->onPendingIntentGetActivity(Landroid/content/Context;Landroid/content/Intent;)V"
            self._run_smalikit(
                file_path=str(target_file),
                method="getActivity(Landroid/content/Context;ILandroid/content/Intent;I)",
                insert_line=["2", hook_code],
            )
            self._run_smalikit(
                file_path=str(target_file),
                method="getActivity(Landroid/content/Context;ILandroid/content/Intent;ILandroid/os/Bundle;)",
                insert_line=["2", hook_code],
            )

        self._integrate_custom_platform_key(wd)
        self._inject_hook_helper_methods(wd)

        # Fix Voice Trigger for A16
        if int(self.ctx.port_android_version) >= 16:
            st_config = self._find_file(wd, "SoundTrigger$RecognitionConfig.smali")
            if st_config:
                self.logger.info(
                    f"Applying VoiceTrigger compatibility patch to {st_config.name}..."
                )
                content = st_config.read_text(encoding="utf-8", errors="ignore")

                field_def = ".field public captureRequested:Z"
                if field_def not in content:
                    target_field = ".field private final blacklist mCaptureRequested:Z"
                    if target_field in content:
                        content = content.replace(target_field, f"{target_field}\n{field_def}")
                        st_config.write_text(content, encoding="utf-8")
                        self.logger.info("  -> Added field captureRequested")

                constructor_sig = "<init>(ZZ[Landroid/hardware/soundtrigger/SoundTrigger$KeyphraseRecognitionExtra;[BI)V"
                old_iput = "iput-boolean p1, p0, Landroid/hardware/soundtrigger/SoundTrigger$RecognitionConfig;->mCaptureRequested:Z"

                self._run_smalikit(
                    file_path=str(st_config),
                    method=constructor_sig,
                    after_line=[
                        old_iput,
                        "iput-boolean p1, p0, Landroid/hardware/soundtrigger/SoundTrigger$RecognitionConfig;->captureRequested:Z",
                    ],
                )

        self._apkeditor_build(wd, jar)

    def _inject_hook_helper_methods(self, work_dir: Path) -> None:
        """Inject HookHelper additional methods (AutoCopy)."""

        hook_helper = self._find_file(work_dir, "HookHelper.smali")
        if not hook_helper:
            self.logger.warning("HookHelper.smali not found, creating new one...")
            return

        self.logger.info(f"Injecting implementation into {hook_helper.name}...")

        smali_code = r"""
.method public static onPendingIntentGetActivity(Landroid/content/Context;Landroid/content/Intent;)V
    .locals 5

    .line 100
    if-eqz p1, :cond_end

    # Check for extras
    invoke-virtual {p1}, Landroid/content/Intent;->getExtras()Landroid/os/Bundle;
    move-result-object v0
    if-nez v0, :cond_check_clip

    goto :cond_end

    :cond_check_clip
    # Try to find "sms_body" or typical keys
    const-string v1, "android.intent.extra.TEXT"
    invoke-virtual {v0, v1}, Landroid/os/Bundle;->getString(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v1

    if-nez v1, :cond_check_body
    const-string v1, "sms_body"
    invoke-virtual {v0, v1}, Landroid/os/Bundle;->getString(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v1

    :cond_check_body
    if-nez v1, :cond_scan_match
    goto :cond_end

    :cond_scan_match
    # Now v1 is the content string. Run Regex.
    # Regex: (?<![0-9])([0-9]{4,6})(?![0-9])

    const-string v2, "(?<![0-9])([0-9]{4,6})(?![0-9])"
    invoke-static {v2}, Ljava/util/regex/Pattern;->compile(Ljava/lang/String;)Ljava/util/regex/Pattern;
    move-result-object v2
    invoke-virtual {v2, v1}, Ljava/util/regex/Pattern;->matcher(Ljava/lang/CharSequence;)Ljava/util/regex/Matcher;
    move-result-object v2

    invoke-virtual {v2}, Ljava/util/regex/Matcher;->find()Z
    move-result v3
    if-eqz v3, :cond_end

    # Found match! Group 1 is the code
    const/4 v3, 0x1
    invoke-virtual {v2, v3}, Ljava/util/regex/Matcher;->group(I)Ljava/lang/String;
    move-result-object v2

    if-eqz v2, :cond_end

    # Copy to Clipboard
    const-string v3, "clipboard"
    invoke-virtual {p0, v3}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;
    move-result-object v3
    check-cast v3, Landroid/content/ClipboardManager;

    if-eqz v3, :cond_end

    # ClipData.newPlainText("Verification Code", code)
    const-string v4, "Verification Code"
    invoke-static {v4, v2}, Landroid/content/ClipData;->newPlainText(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Landroid/content/ClipData;
    move-result-object v2

    invoke-virtual {v3, v2}, Landroid/content/ClipboardManager;->setPrimaryClip(Landroid/content/ClipData;)V

    :cond_end
    return-void
.end method
"""
        content = hook_helper.read_text(encoding="utf-8")
        if "onPendingIntentGetActivity" not in content:
            with open(hook_helper, "a", encoding="utf-8") as f:
                f.write(smali_code)
            self.logger.info("Added onPendingIntentGetActivity to HookHelper.")
        else:
            self.logger.info("onPendingIntentGetActivity already exists.")

    def _integrate_custom_platform_key(self, work_dir: Path) -> None:
        """Inject custom platform key check into ExtraPackageManager."""
        epm_smali = self._find_file(work_dir, "ExtraPackageManager.smali")
        if not epm_smali:
            return

        self.logger.info("Injecting Custom Platform Key Check...")

        hook_code = f"""
    # [Start] Custom Platform Key Check
    const/4 v2, 0x1
    new-array v2, v2, [Landroid/content/pm/Signature;
    new-instance v3, Landroid/content/pm/Signature;
    const-string v4, "{MY_PLATFORM_KEY}"
    invoke-direct {{v3, v4}}, Landroid/content/pm/Signature;-><init>(Ljava/lang/String;)V
    const/4 v4, 0x0
    aput-object v3, v2, v4
    invoke-static {{p0, v2}}, Lmiui/content/pm/ExtraPackageManager;->compareSignatures([Landroid/content/pm/Signature;[Landroid/content/pm/Signature;)I
    move-result v2
    if-eqz v2, :cond_custom_skip
    const/4 v2, 0x1
    return v2
    :cond_custom_skip
    # [End]"""

        self._run_smalikit(
            file_path=str(epm_smali),
            method="isTrustedPlatformSignature([Landroid/content/pm/Signature;)Z",
            regex_replace=(r"\.locals\s+\d+", ".locals 5"),
        )
        self._run_smalikit(
            file_path=str(epm_smali),
            method="isTrustedPlatformSignature([Landroid/content/pm/Signature;)Z",
            insert_line=["2", hook_code],
        )

    def _inject_xeu_toolbox(self) -> None:
        """Inject Xiaomi.eu Toolbox."""
        xeu_zip = Path("devices/common/xeutoolbox.zip")
        if not xeu_zip.exists():
            return

        self.logger.info("Injecting Xiaomi.eu Toolbox...")

        try:
            with zipfile.ZipFile(xeu_zip, "r") as z:
                z.extractall(self.ctx.target_dir)
            self.logger.info(f"Extracted {xeu_zip.name}")
        except Exception as e:
            self.logger.error(f"Failed to extract xeutoolbox: {e}")
            return

        target_files = [
            self.ctx.target_dir / "config/system_ext_file_contexts",
            self.ctx.target_dir / "system_ext/etc/selinux/system_ext_file_contexts",
        ]

        context_line = "\n/system_ext/xbin/xeu_toolbox  u:object_r:toolbox_exec:s0\n"

        for f in target_files:
            if f.exists():
                try:
                    with open(f, "a", encoding="utf-8") as file:
                        file.write(context_line)
                    self.logger.info(f"Updated contexts: {f.name}")
                except Exception as e:
                    self.logger.warning(f"Failed to append context to {f}: {e}")

        cil_file = self.ctx.target_dir / "system_ext/etc/selinux/system_ext_sepolicy.cil"
        policy_line = "\n(allow init toolbox_exec (file ((execute_no_trans))))\n"

        if cil_file.exists():
            try:
                with open(cil_file, "a", encoding="utf-8") as cil_handle:
                    cil_handle.write(policy_line)
                self.logger.info(f"Updated sepolicy: {cil_file.name}")
            except Exception as e:
                self.logger.warning(f"Failed to append policy to {cil_file}: {e}")
