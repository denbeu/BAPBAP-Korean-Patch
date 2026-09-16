using System.Buffers.Binary;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using AssetsTools.NET;
using AssetsTools.NET.Extra;

internal static class Program
{
    private const int TextAssetClassId = 49;
    private const int MonoBehaviourClassId = 114;
    private const long DefaultTargetPathId = 2928;
    private const string DefaultTargetName = "turkish";
    private const int DefaultExpectedRows = 1690;
    private const long LocalisationConfigurationPathId = 104749;

    private static readonly IReadOnlyDictionary<long, string> KnownLocalizationTextAssets =
        new Dictionary<long, string>
        {
            [2921] = "english",
            [2922] = "profanity_english",
            [2923] = "spanish",
            [2924] = "japanese",
            [2925] = "chinese(simplified)",
            [2926] = "portuguese(br)",
            [2927] = "russian",
            [2928] = "turkish",
            [2929] = "french",
            [2930] = "keys",
            [2931] = "german",
            [2932] = "dutch"
        };

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0 || IsHelp(args[0]))
            {
                PrintUsage();
                return args.Length == 0 ? 2 : 0;
            }

            return args[0].ToLowerInvariant() switch
            {
                "inspect" => RunInspect(args[1..]),
                "replace" => RunReplace(args[1..]),
                "verify" => RunVerify(args[1..]),
                "replace-string" => RunReplaceString(args[1..]),
                "verify-string" => RunVerifyString(args[1..]),
                "patch-string-set" => RunPatchStringSet(args[1..]),
                "patch-font-fallback" => RunPatchFontFallback(args[1..]),
                "verify-font-fallback" => RunVerifyFontFallback(args[1..]),
                "patch-font-setting" => RunPatchFontSetting(args[1..]),
                "verify-font-setting" => RunVerifyFontSetting(args[1..]),
                _ => Fail($"Unknown command: {args[0]}")
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"error: {ex.Message}");
            return 1;
        }
    }

    private static int RunInspect(string[] args)
    {
        var options = ParseOptions(args);
        string input = RequirePath(options, "--input");
        AssetSelector selector = ParseSelector(options);
        int previewBytes = ParsePositiveInt(options, "--preview-bytes", 240);

        using var context = AssetContext.Open(input);
        TextAssetRecord record = context.Find(selector);
        PrintRecord(input, record, previewBytes);
        return 0;
    }

    private static int RunReplace(string[] args)
    {
        var options = ParseOptions(args);
        string input = RequirePath(options, "--input");
        string output = RequireValue(options, "--output");
        string payloadPath = RequirePath(options, "--payload");
        AssetSelector selector = ParseSelector(options);

        string inputFullPath = Path.GetFullPath(input);
        string outputFullPath = Path.GetFullPath(output);
        if (string.Equals(inputFullPath, outputFullPath, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--output must be a different file. In-place replacement is intentionally disabled.");

        if (File.Exists(outputFullPath))
            throw new IOException($"Output already exists: {outputFullPath}");

        string? outputDirectory = Path.GetDirectoryName(outputFullPath);
        if (!string.IsNullOrEmpty(outputDirectory))
            Directory.CreateDirectory(outputDirectory);

        byte[] replacement = File.ReadAllBytes(payloadPath);

        TextAssetRecord before;
        long targetPathId;
        string targetName;
        using (var context = AssetContext.Open(inputFullPath))
        {
            before = context.Find(selector);
            targetPathId = before.PathId;
            targetName = before.Name;

            byte[] rebuilt = TextAssetCodec.ReplaceScript(before.SerializedBytes, replacement);
            before.Info.SetNewData(rebuilt);

            using var outputStream = new FileStream(outputFullPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            using var writer = new AssetsFileWriter(outputStream);
            context.File.Write(writer, 0);
        }

        using var verification = AssetContext.Open(outputFullPath);
        TextAssetRecord after = verification.Find(new AssetSelector(targetPathId, null));
        if (!after.ScriptBytes.AsSpan().SequenceEqual(replacement))
            throw new InvalidDataException("Verification failed: reopened m_Script payload does not match the requested bytes.");
        if (!string.Equals(after.Name, targetName, StringComparison.Ordinal))
            throw new InvalidDataException("Verification failed: TextAsset m_Name changed unexpectedly.");

        Console.WriteLine("replacement verified");
        Console.WriteLine($"input:  {inputFullPath}");
        Console.WriteLine($"output: {outputFullPath}");
        Console.WriteLine($"pathId: {after.PathId}");
        Console.WriteLine($"name:   {after.Name}");
        Console.WriteLine($"before-bytes: {before.ScriptBytes.Length}");
        Console.WriteLine($"after-bytes:  {after.ScriptBytes.Length}");
        Console.WriteLine($"sha256: {Convert.ToHexString(SHA256.HashData(after.ScriptBytes)).ToLowerInvariant()}");
        return 0;
    }

    private static int RunVerify(string[] args)
    {
        var options = ParseOptions(args);
        string originalPath = Path.GetFullPath(RequirePath(options, "--original"));
        string patchedPath = Path.GetFullPath(RequirePath(options, "--patched"));
        string payloadPath = Path.GetFullPath(RequirePath(options, "--payload"));
        long targetPathId = ParseLong(options, "--target-path-id", DefaultTargetPathId);
        string targetName = GetOptionalValue(options, "--target-name") ??
            (KnownLocalizationTextAssets.TryGetValue(targetPathId, out string? knownName) ? knownName : DefaultTargetName);
        int expectedRows = ParsePositiveInt(options, "--expected-rows", DefaultExpectedRows);

        byte[] expectedPayload = File.ReadAllBytes(payloadPath);
        var failures = new List<string>();

        int payloadRows = TryCountLocalizationRows(expectedPayload, "expected payload", failures);
        if (payloadRows >= 0 && payloadRows != expectedRows)
            failures.Add($"expected payload row count is {payloadRows}, expected {expectedRows}");

        using var original = AssetContext.Open(originalPath);
        using var patched = AssetContext.Open(patchedPath);

        TextAssetRecord? originalTarget = TryReadTextAsset(original, targetPathId, "original target", failures);
        TextAssetRecord? patchedTarget = TryReadTextAsset(patched, targetPathId, "patched target", failures);

        if (originalTarget is not null && !string.Equals(originalTarget.Name, targetName, StringComparison.Ordinal))
            failures.Add($"original target PathID {targetPathId} name is '{originalTarget.Name}', expected '{targetName}'");

        if (patchedTarget is not null)
        {
            if (!string.Equals(patchedTarget.Name, targetName, StringComparison.Ordinal))
                failures.Add($"patched target PathID {targetPathId} name is '{patchedTarget.Name}', expected '{targetName}'");

            if (!patchedTarget.ScriptBytes.AsSpan().SequenceEqual(expectedPayload))
                failures.Add($"patched target PathID {targetPathId} m_Script bytes do not match --payload");

            int actualRows = TryCountLocalizationRows(patchedTarget.ScriptBytes, "patched target", failures);
            if (actualRows >= 0 && actualRows != expectedRows)
                failures.Add($"patched target row count is {actualRows}, expected {expectedRows}");
        }

        int originalLocalizationCount = VerifyLocalizationInventory(original, "original", failures);
        int patchedLocalizationCount = VerifyLocalizationInventory(patched, "patched", failures);
        VerifyConfiguration(original, patched, failures);

        MetadataComparison comparison = CompareMetadata(original, patched, targetPathId, failures);

        if (originalTarget is not null && patchedTarget is not null)
        {
            byte[] expectedSerialized = TextAssetCodec.ReplaceScript(originalTarget.SerializedBytes, expectedPayload);
            if (!patchedTarget.SerializedBytes.AsSpan().SequenceEqual(expectedSerialized))
                failures.Add($"patched target PathID {targetPathId} serialized bytes differ outside the expected m_Script replacement");
        }

        Console.WriteLine("asset QA inventory");
        Console.WriteLine($"original: {originalPath}");
        Console.WriteLine($"patched:  {patchedPath}");
        Console.WriteLine($"target:   PathID {targetPathId} / {targetName} / class {TextAssetClassId}");
        Console.WriteLine($"payload:  {expectedPayload.Length} bytes / {Math.Max(payloadRows, 0)} rows / sha256 {Sha256(expectedPayload)}");
        Console.WriteLine($"localization TextAssets present: original {originalLocalizationCount}/{KnownLocalizationTextAssets.Count}, patched {patchedLocalizationCount}/{KnownLocalizationTextAssets.Count}");
        Console.WriteLine($"LocalisationConfiguration present: original {original.GetInfo(LocalisationConfigurationPathId) is not null}, patched {patched.GetInfo(LocalisationConfigurationPathId) is not null} (PathID {LocalisationConfigurationPathId})");
        Console.WriteLine($"metadata assets: original {comparison.OriginalCount}, patched {comparison.PatchedCount}");
        Console.WriteLine($"non-target offset changes: {comparison.NonTargetOffsetChanges} (expected shift: {comparison.ExpectedOffsetShift:+#;-#;0} bytes after target)");

        if (failures.Count > 0)
        {
            Console.Error.WriteLine($"asset QA failed ({failures.Count} issue(s)):");
            foreach (string failure in failures)
                Console.Error.WriteLine($"  - {failure}");
            return 1;
        }

        Console.WriteLine("asset QA passed");
        return 0;
    }

    private static int RunReplaceString(string[] args)
    {
        var options = ParseOptions(args);
        string input = RequirePath(options, "--input");
        string output = RequireValue(options, "--output");
        long pathId = ParseRequiredLong(options, "--path-id");
        string oldValue = RequireValue(options, "--old");
        string newValue = RequireValue(options, "--new");
        int? requestedLengthOffset = ParseOptionalNonNegativeInt(options, "--length-offset");

        string inputFullPath = Path.GetFullPath(input);
        string outputFullPath = Path.GetFullPath(output);
        if (string.Equals(inputFullPath, outputFullPath, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--output must be a different file. In-place replacement is intentionally disabled.");
        if (File.Exists(outputFullPath))
            throw new IOException($"Output already exists: {outputFullPath}");

        string? outputDirectory = Path.GetDirectoryName(outputFullPath);
        if (!string.IsNullOrEmpty(outputDirectory))
            Directory.CreateDirectory(outputDirectory);

        byte[] originalObject;
        byte[] expectedObject;
        int originalTypeId;
        int lengthOffset;
        using (var context = AssetContext.Open(inputFullPath))
        {
            AssetFileInfo info = context.GetInfo(pathId) ?? throw new KeyNotFoundException($"PathID {pathId} was not found.");
            originalTypeId = info.TypeId;
            if (originalTypeId != MonoBehaviourClassId)
                throw new InvalidDataException($"PathID {pathId} has class ID {originalTypeId}, expected MonoBehaviour ({MonoBehaviourClassId}).");

            originalObject = context.ReadSerializedBytes(info);
            expectedObject = requestedLengthOffset is int exactOffset
                ? SerializedStringCodec.ReplaceAt(originalObject, oldValue, newValue, exactOffset, out lengthOffset)
                : SerializedStringCodec.ReplaceUnique(originalObject, oldValue, newValue, out lengthOffset);
            info.SetNewData(expectedObject);

            using var outputStream = new FileStream(outputFullPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            using var writer = new AssetsFileWriter(outputStream);
            context.File.Write(writer, 0);
        }

        using var verification = AssetContext.Open(outputFullPath);
        AssetFileInfo verifiedInfo = verification.GetInfo(pathId) ?? throw new InvalidDataException($"Verification failed: PathID {pathId} disappeared.");
        if (verifiedInfo.TypeId != originalTypeId)
            throw new InvalidDataException($"Verification failed: PathID {pathId} class changed from {originalTypeId} to {verifiedInfo.TypeId}.");
        byte[] actualObject = verification.ReadSerializedBytes(verifiedInfo);
        if (!actualObject.AsSpan().SequenceEqual(expectedObject))
            throw new InvalidDataException("Verification failed: reopened serialized object does not match the deterministic string-field replacement.");

        Console.WriteLine("serialized string replacement verified");
        Console.WriteLine($"input:         {inputFullPath}");
        Console.WriteLine($"output:        {outputFullPath}");
        Console.WriteLine($"pathId:        {pathId}");
        Console.WriteLine($"classId:       {originalTypeId}");
        Console.WriteLine($"length-offset: {lengthOffset}");
        Console.WriteLine($"before-bytes:  {originalObject.Length}");
        Console.WriteLine($"after-bytes:   {actualObject.Length}");
        Console.WriteLine($"before-value:  {oldValue}");
        Console.WriteLine($"after-value:   {newValue}");
        Console.WriteLine($"object-sha256: {Sha256(actualObject)}");
        return 0;
    }

    private static int RunVerifyString(string[] args)
    {
        var options = ParseOptions(args);
        string originalPath = Path.GetFullPath(RequirePath(options, "--original"));
        string patchedPath = Path.GetFullPath(RequirePath(options, "--patched"));
        long pathId = ParseRequiredLong(options, "--path-id");
        string oldValue = RequireValue(options, "--old");
        string newValue = RequireValue(options, "--new");
        int? requestedLengthOffset = ParseOptionalNonNegativeInt(options, "--length-offset");

        var failures = new List<string>();
        using var original = AssetContext.Open(originalPath);
        using var patched = AssetContext.Open(patchedPath);

        AssetFileInfo? originalInfo = original.GetInfo(pathId);
        AssetFileInfo? patchedInfo = patched.GetInfo(pathId);
        if (originalInfo is null)
            failures.Add($"original PathID {pathId} is missing");
        if (patchedInfo is null)
            failures.Add($"patched PathID {pathId} is missing");

        int lengthOffset = -1;
        if (originalInfo is not null && patchedInfo is not null)
        {
            if (originalInfo.TypeId != MonoBehaviourClassId)
                failures.Add($"original PathID {pathId} has class ID {originalInfo.TypeId}, expected MonoBehaviour ({MonoBehaviourClassId})");
            if (patchedInfo.TypeId != originalInfo.TypeId)
                failures.Add($"patched PathID {pathId} class changed from {originalInfo.TypeId} to {patchedInfo.TypeId}");

            byte[] originalBytes = original.ReadSerializedBytes(originalInfo);
            byte[] patchedBytes = patched.ReadSerializedBytes(patchedInfo);
            try
            {
                byte[] expectedBytes = requestedLengthOffset is int exactOffset
                    ? SerializedStringCodec.ReplaceAt(originalBytes, oldValue, newValue, exactOffset, out lengthOffset)
                    : SerializedStringCodec.ReplaceUnique(originalBytes, oldValue, newValue, out lengthOffset);
                if (!patchedBytes.AsSpan().SequenceEqual(expectedBytes))
                    failures.Add($"PathID {pathId} serialized bytes do not match the deterministic '{oldValue}' -> '{newValue}' replacement");
            }
            catch (Exception ex) when (ex is InvalidDataException or ArgumentException)
            {
                failures.Add($"could not construct expected serialized replacement for PathID {pathId}: {ex.Message}");
            }
        }

        MetadataComparison comparison = CompareMetadata(original, patched, pathId, failures);
        Console.WriteLine("serialized string patch QA");
        Console.WriteLine($"original: {originalPath}");
        Console.WriteLine($"patched:  {patchedPath}");
        Console.WriteLine($"target:   PathID {pathId} / class {MonoBehaviourClassId}");
        Console.WriteLine($"field length offset: {lengthOffset}");
        Console.WriteLine($"expected replacement: '{oldValue}' -> '{newValue}'");
        Console.WriteLine($"metadata assets: original {comparison.OriginalCount}, patched {comparison.PatchedCount}");
        Console.WriteLine($"non-target offset changes: {comparison.NonTargetOffsetChanges} (expected shift: {comparison.ExpectedOffsetShift:+#;-#;0} bytes after target)");

        if (failures.Count > 0)
        {
            Console.Error.WriteLine($"serialized string patch QA failed ({failures.Count} issue(s)):");
            foreach (string failure in failures)
                Console.Error.WriteLine($"  - {failure}");
            return 1;
        }

        Console.WriteLine("serialized string patch QA passed");
        return 0;
    }

    private static int RunPatchStringSet(string[] args)
    {
        var options = ParseOptions(args);
        string inputFullPath = Path.GetFullPath(RequirePath(options, "--input"));
        string outputFullPath = Path.GetFullPath(RequireValue(options, "--output"));
        string specPath = Path.GetFullPath(RequirePath(options, "--spec"));
        if (string.Equals(inputFullPath, outputFullPath, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--output must be a different file. In-place replacement is intentionally disabled.");
        if (File.Exists(outputFullPath))
            throw new IOException($"Output already exists: {outputFullPath}");

        SerializedStringPatchDocument patchDocument = LoadSerializedStringPatchDocument(specPath);
        if (patchDocument.SerializedStringPatches.Count == 0)
            throw new InvalidDataException("serialized string patch spec contains no patches");

        string? outputDirectory = Path.GetDirectoryName(outputFullPath);
        if (!string.IsNullOrEmpty(outputDirectory))
            Directory.CreateDirectory(outputDirectory);

        var expectedByPathId = new Dictionary<long, byte[]>();
        var originalTypeByPathId = new Dictionary<long, int>();
        using (var context = AssetContext.Open(inputFullPath))
        {
            foreach (IGrouping<long, SerializedStringPatchSpec> group in patchDocument.SerializedStringPatches.GroupBy(patch => patch.PathId))
            {
                AssetFileInfo info = context.GetInfo(group.Key) ?? throw new KeyNotFoundException($"PathID {group.Key} was not found.");
                if (info.TypeId != MonoBehaviourClassId)
                    throw new InvalidDataException($"PathID {group.Key} has class ID {info.TypeId}, expected MonoBehaviour ({MonoBehaviourClassId}).");
                originalTypeByPathId[group.Key] = info.TypeId;
                byte[] rebuilt = context.ReadSerializedBytes(info);

                foreach (SerializedStringPatchSpec patch in group)
                {
                    int actualOffset;
                    rebuilt = patch.LengthOffset is int exactOffset
                        ? SerializedStringCodec.ReplaceAt(rebuilt, patch.Original, patch.Patched, exactOffset, out actualOffset)
                        : SerializedStringCodec.ReplaceUnique(rebuilt, patch.Original, patch.Patched, out actualOffset);
                    Console.WriteLine($"patch PathID {patch.PathId} / {patch.Field}: '{patch.Original}' -> '{patch.Patched}' @ {actualOffset}");
                }

                expectedByPathId[group.Key] = rebuilt;
                info.SetNewData(rebuilt);
            }

            using var outputStream = new FileStream(outputFullPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            using var writer = new AssetsFileWriter(outputStream);
            context.File.Write(writer, 0);
        }

        using var verification = AssetContext.Open(outputFullPath);
        foreach ((long pathId, byte[] expected) in expectedByPathId)
        {
            AssetFileInfo info = verification.GetInfo(pathId) ?? throw new InvalidDataException($"Verification failed: PathID {pathId} disappeared.");
            if (info.TypeId != originalTypeByPathId[pathId])
                throw new InvalidDataException($"Verification failed: PathID {pathId} class changed.");
            byte[] actual = verification.ReadSerializedBytes(info);
            if (!actual.AsSpan().SequenceEqual(expected))
                throw new InvalidDataException($"Verification failed: PathID {pathId} does not match deterministic patch-set output.");
        }

        Console.WriteLine("serialized string patch set verified");
        Console.WriteLine($"input:   {inputFullPath}");
        Console.WriteLine($"output:  {outputFullPath}");
        Console.WriteLine($"spec:    {specPath}");
        Console.WriteLine($"patches: {patchDocument.SerializedStringPatches.Count}");
        Console.WriteLine($"objects: {expectedByPathId.Count}");
        return 0;
    }

    private static SerializedStringPatchDocument LoadSerializedStringPatchDocument(string specPath)
    {
        string json = File.ReadAllText(specPath, Encoding.UTF8);
        SerializedStringPatchDocument? document = JsonSerializer.Deserialize<SerializedStringPatchDocument>(json);
        if (document is null)
            throw new InvalidDataException($"could not deserialize serialized string patch spec: {specPath}");
        foreach (SerializedStringPatchSpec patch in document.SerializedStringPatches)
        {
            if (patch.PathId <= 0)
                throw new InvalidDataException("serialized string patch path_id must be positive");
            if (string.IsNullOrEmpty(patch.Original))
                throw new InvalidDataException($"PathID {patch.PathId} serialized string patch original value is empty");
            if (string.Equals(patch.Original, patch.Patched, StringComparison.Ordinal))
                throw new InvalidDataException($"PathID {patch.PathId} serialized string patch does not change the value");
            if (patch.LengthOffset is int offset && (offset < 0 || offset % 4 != 0))
                throw new InvalidDataException($"PathID {patch.PathId} serialized string patch length_offset must be non-negative and 4-byte aligned");
        }
        return document;
    }

    private static int RunPatchFontFallback(string[] args)
    {
        var options = ParseOptions(args);
        string inputFullPath = Path.GetFullPath(RequirePath(options, "--input"));
        string outputFullPath = Path.GetFullPath(RequireValue(options, "--output"));
        string specPath = Path.GetFullPath(RequirePath(options, "--spec"));
        int patchIndex = ParsePositiveInt(options, "--patch-index", -1);
        if (patchIndex < 0)
            throw new ArgumentException("--patch-index is required and must be non-negative.");
        if (string.Equals(inputFullPath, outputFullPath, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--output must be a different file. In-place replacement is intentionally disabled.");
        if (File.Exists(outputFullPath))
            throw new IOException($"Output already exists: {outputFullPath}");

        FontFallbackPatchSpec patch = LoadFontFallbackPatch(specPath, patchIndex);
        string? outputDirectory = Path.GetDirectoryName(outputFullPath);
        if (!string.IsNullOrEmpty(outputDirectory))
            Directory.CreateDirectory(outputDirectory);

        byte[] originalObject;
        byte[] expectedObject;
        using (var context = AssetContext.Open(inputFullPath))
        {
            AssetFileInfo info = context.GetInfo(patch.PathId) ?? throw new KeyNotFoundException($"PathID {patch.PathId} was not found.");
            if (info.TypeId != MonoBehaviourClassId)
                throw new InvalidDataException($"PathID {patch.PathId} has class ID {info.TypeId}, expected MonoBehaviour ({MonoBehaviourClassId}).");

            originalObject = context.ReadSerializedBytes(info);
            TmpFontAssetFallbackCodec.ValidateFontAssetIdentity(originalObject, patch.ObjectName);
            ValidateFallbackTargets(context, originalObject, patch);
            expectedObject = TmpFontAssetFallbackCodec.AppendReferences(originalObject, patch, out _);
            info.SetNewData(expectedObject);

            using var outputStream = new FileStream(outputFullPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            using var writer = new AssetsFileWriter(outputStream);
            context.File.Write(writer, 0);
        }

        using var verification = AssetContext.Open(outputFullPath);
        AssetFileInfo verifiedInfo = verification.GetInfo(patch.PathId) ?? throw new InvalidDataException($"Verification failed: PathID {patch.PathId} disappeared.");
        if (verifiedInfo.TypeId != MonoBehaviourClassId)
            throw new InvalidDataException($"Verification failed: PathID {patch.PathId} class changed to {verifiedInfo.TypeId}.");
        byte[] actualObject = verification.ReadSerializedBytes(verifiedInfo);
        if (!actualObject.AsSpan().SequenceEqual(expectedObject))
            throw new InvalidDataException("Verification failed: reopened FontAsset object does not match the deterministic fallback-table rebuild.");
        TmpFontAssetFallbackCodec.ValidateFontAssetIdentity(actualObject, patch.ObjectName);
        ValidateFallbackTargets(verification, actualObject, patch);

        Console.WriteLine("TMP FontAsset fallback patch verified");
        Console.WriteLine($"input:          {inputFullPath}");
        Console.WriteLine($"output:         {outputFullPath}");
        Console.WriteLine($"pathId:         {patch.PathId}");
        Console.WriteLine($"name:           {patch.ObjectName}");
        Console.WriteLine($"field:          {patch.Field}");
        Console.WriteLine($"field-offset:   {patch.FieldOffset}");
        Console.WriteLine($"before-entries: {FormatRefs(patch.ExistingRefs)}");
        Console.WriteLine($"append-entries: {FormatRefs(patch.AppendRefs)}");
        Console.WriteLine($"before-bytes:   {originalObject.Length}");
        Console.WriteLine($"after-bytes:    {actualObject.Length}");
        Console.WriteLine($"object-sha256:  {Sha256(actualObject)}");
        return 0;
    }

    private static int RunVerifyFontFallback(string[] args)
    {
        var options = ParseOptions(args);
        string originalPath = Path.GetFullPath(RequirePath(options, "--original"));
        string patchedPath = Path.GetFullPath(RequirePath(options, "--patched"));
        string specPath = Path.GetFullPath(RequirePath(options, "--spec"));
        int patchIndex = ParsePositiveInt(options, "--patch-index", -1);
        if (patchIndex < 0)
            throw new ArgumentException("--patch-index is required and must be non-negative.");

        FontFallbackPatchSpec patch = LoadFontFallbackPatch(specPath, patchIndex);
        var failures = new List<string>();
        using var original = AssetContext.Open(originalPath);
        using var patched = AssetContext.Open(patchedPath);
        AssetFileInfo? originalInfo = original.GetInfo(patch.PathId);
        AssetFileInfo? patchedInfo = patched.GetInfo(patch.PathId);
        if (originalInfo is null)
            failures.Add($"original PathID {patch.PathId} is missing");
        if (patchedInfo is null)
            failures.Add($"patched PathID {patch.PathId} is missing");

        if (originalInfo is not null && patchedInfo is not null)
        {
            if (originalInfo.TypeId != MonoBehaviourClassId)
                failures.Add($"original PathID {patch.PathId} has class ID {originalInfo.TypeId}, expected MonoBehaviour ({MonoBehaviourClassId})");
            if (patchedInfo.TypeId != originalInfo.TypeId)
                failures.Add($"patched PathID {patch.PathId} class changed from {originalInfo.TypeId} to {patchedInfo.TypeId}");
            try
            {
                byte[] originalBytes = original.ReadSerializedBytes(originalInfo);
                byte[] patchedBytes = patched.ReadSerializedBytes(patchedInfo);
                TmpFontAssetFallbackCodec.ValidateFontAssetIdentity(originalBytes, patch.ObjectName);
                TmpFontAssetFallbackCodec.ValidateFontAssetIdentity(patchedBytes, patch.ObjectName);
                ValidateFallbackTargets(original, originalBytes, patch);
                ValidateFallbackTargets(patched, patchedBytes, patch);
                byte[] expectedBytes = TmpFontAssetFallbackCodec.AppendReferences(originalBytes, patch, out _);
                if (!patchedBytes.AsSpan().SequenceEqual(expectedBytes))
                    failures.Add($"PathID {patch.PathId} serialized bytes differ outside the expected {patch.Field} append");
            }
            catch (Exception ex) when (ex is InvalidDataException or ArgumentException or KeyNotFoundException)
            {
                failures.Add($"could not verify FontAsset fallback patch for PathID {patch.PathId}: {ex.Message}");
            }
        }

        Console.WriteLine("TMP FontAsset fallback patch QA");
        Console.WriteLine($"original: {originalPath}");
        Console.WriteLine($"patched:  {patchedPath}");
        Console.WriteLine($"target:   PathID {patch.PathId} / {patch.ObjectName}");
        Console.WriteLine($"field:    {patch.Field} @ {patch.FieldOffset}");
        Console.WriteLine($"old refs: {FormatRefs(patch.ExistingRefs)}");
        Console.WriteLine($"new refs: {FormatRefs(patch.AppendRefs)}");

        if (failures.Count > 0)
        {
            Console.Error.WriteLine($"TMP FontAsset fallback patch QA failed ({failures.Count} issue(s)):");
            foreach (string failure in failures)
                Console.Error.WriteLine($"  - {failure}");
            return 1;
        }

        Console.WriteLine("TMP FontAsset fallback patch QA passed");
        return 0;
    }

    private static int RunPatchFontSetting(string[] args)
    {
        var options = ParseOptions(args);
        string inputFullPath = Path.GetFullPath(RequirePath(options, "--input"));
        string outputFullPath = Path.GetFullPath(RequireValue(options, "--output"));
        string specPath = Path.GetFullPath(RequirePath(options, "--spec"));
        int patchIndex = ParsePositiveInt(options, "--patch-index", -1);
        if (patchIndex < 0)
            throw new ArgumentException("--patch-index is required and must be non-negative.");
        if (string.Equals(inputFullPath, outputFullPath, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--output must be a different file. In-place replacement is intentionally disabled.");
        if (File.Exists(outputFullPath))
            throw new IOException($"Output already exists: {outputFullPath}");

        FontSettingPatchSpec patch = LoadFontSettingPatch(specPath, patchIndex);
        string? outputDirectory = Path.GetDirectoryName(outputFullPath);
        if (!string.IsNullOrEmpty(outputDirectory))
            Directory.CreateDirectory(outputDirectory);

        byte[] originalObject;
        byte[] expectedObject;
        using (var context = AssetContext.Open(inputFullPath))
        {
            AssetFileInfo info = context.GetInfo(patch.PathId) ?? throw new KeyNotFoundException($"PathID {patch.PathId} was not found.");
            if (info.TypeId != MonoBehaviourClassId)
                throw new InvalidDataException($"PathID {patch.PathId} has class ID {info.TypeId}, expected MonoBehaviour ({MonoBehaviourClassId}).");
            originalObject = context.ReadSerializedBytes(info);
            ValidateFontSettingIdentity(originalObject, patch, expectPatchedValue: false);
            expectedObject = TmpFontAssetSettingCodec.ReplaceBool(originalObject, patch);
            info.SetNewData(expectedObject);

            using var outputStream = new FileStream(outputFullPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            using var writer = new AssetsFileWriter(outputStream);
            context.File.Write(writer, 0);
        }

        using var verification = AssetContext.Open(outputFullPath);
        AssetFileInfo verifiedInfo = verification.GetInfo(patch.PathId) ?? throw new InvalidDataException($"Verification failed: PathID {patch.PathId} disappeared.");
        if (verifiedInfo.TypeId != MonoBehaviourClassId)
            throw new InvalidDataException($"Verification failed: PathID {patch.PathId} class changed to {verifiedInfo.TypeId}.");
        byte[] actualObject = verification.ReadSerializedBytes(verifiedInfo);
        ValidateFontSettingIdentity(actualObject, patch, expectPatchedValue: true);
        if (!actualObject.AsSpan().SequenceEqual(expectedObject))
            throw new InvalidDataException("Verification failed: reopened FontAsset object does not match the deterministic setting replacement.");

        Console.WriteLine("TMP FontAsset setting patch verified");
        Console.WriteLine($"input:         {inputFullPath}");
        Console.WriteLine($"output:        {outputFullPath}");
        Console.WriteLine($"pathId:        {patch.PathId}");
        Console.WriteLine($"name:          {patch.ObjectName}");
        Console.WriteLine($"field:         {patch.Field}");
        Console.WriteLine($"field-offset:  {patch.FieldOffset}");
        Console.WriteLine($"before-value:  {patch.Original}");
        Console.WriteLine($"after-value:   {patch.Patched}");
        Console.WriteLine($"object-sha256: {Sha256(actualObject)}");
        return 0;
    }

    private static int RunVerifyFontSetting(string[] args)
    {
        var options = ParseOptions(args);
        string originalPath = Path.GetFullPath(RequirePath(options, "--original"));
        string patchedPath = Path.GetFullPath(RequirePath(options, "--patched"));
        string specPath = Path.GetFullPath(RequirePath(options, "--spec"));
        int patchIndex = ParsePositiveInt(options, "--patch-index", -1);
        if (patchIndex < 0)
            throw new ArgumentException("--patch-index is required and must be non-negative.");

        FontSettingPatchSpec patch = LoadFontSettingPatch(specPath, patchIndex);
        var failures = new List<string>();
        using var original = AssetContext.Open(originalPath);
        using var patched = AssetContext.Open(patchedPath);
        AssetFileInfo? originalInfo = original.GetInfo(patch.PathId);
        AssetFileInfo? patchedInfo = patched.GetInfo(patch.PathId);
        if (originalInfo is null)
            failures.Add($"original PathID {patch.PathId} is missing");
        if (patchedInfo is null)
            failures.Add($"patched PathID {patch.PathId} is missing");
        if (originalInfo is not null && patchedInfo is not null)
        {
            try
            {
                if (originalInfo.TypeId != MonoBehaviourClassId || patchedInfo.TypeId != originalInfo.TypeId)
                    throw new InvalidDataException("FontAsset MonoBehaviour class identity changed");
                byte[] originalBytes = original.ReadSerializedBytes(originalInfo);
                byte[] patchedBytes = patched.ReadSerializedBytes(patchedInfo);
                ValidateFontSettingIdentity(originalBytes, patch, expectPatchedValue: false);
                ValidateFontSettingIdentity(patchedBytes, patch, expectPatchedValue: true);
                byte[] expectedBytes = TmpFontAssetSettingCodec.ReplaceBool(originalBytes, patch);
                if (!patchedBytes.AsSpan().SequenceEqual(expectedBytes))
                    failures.Add($"PathID {patch.PathId} serialized bytes differ outside the expected {patch.Field} replacement");
            }
            catch (Exception ex) when (ex is InvalidDataException or ArgumentException)
            {
                failures.Add($"could not verify FontAsset setting patch for PathID {patch.PathId}: {ex.Message}");
            }
        }

        Console.WriteLine("TMP FontAsset setting patch QA");
        Console.WriteLine($"original: {originalPath}");
        Console.WriteLine($"patched:  {patchedPath}");
        Console.WriteLine($"target:   PathID {patch.PathId} / {patch.ObjectName}");
        Console.WriteLine($"field:    {patch.Field} @ {patch.FieldOffset} / {patch.Original}->{patch.Patched}");
        if (failures.Count > 0)
        {
            Console.Error.WriteLine($"TMP FontAsset setting patch QA failed ({failures.Count} issue(s)):");
            foreach (string failure in failures)
                Console.Error.WriteLine($"  - {failure}");
            return 1;
        }
        Console.WriteLine("TMP FontAsset setting patch QA passed");
        return 0;
    }

    private static FontFallbackPatchSpec LoadFontFallbackPatch(string specPath, int patchIndex)
    {
        string json = File.ReadAllText(specPath, Encoding.UTF8);
        FontFallbackPatchDocument? document = JsonSerializer.Deserialize<FontFallbackPatchDocument>(json, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        });
        if (document?.FallbackPatches is null)
            throw new InvalidDataException("font fallback patch spec is missing fallback_patches");
        if (patchIndex >= document.FallbackPatches.Count)
            throw new ArgumentOutOfRangeException(nameof(patchIndex), $"patch index {patchIndex} is outside fallback_patches count {document.FallbackPatches.Count}");
        FontFallbackPatchSpec patch = document.FallbackPatches[patchIndex];
        if (!string.Equals(patch.Field, "m_FallbackFontAssetTable", StringComparison.Ordinal))
            throw new InvalidDataException($"unsupported FontAsset fallback field '{patch.Field}'");
        if (patch.PathId <= 0 || string.IsNullOrWhiteSpace(patch.ObjectName) || patch.FieldOffset < 0)
            throw new InvalidDataException($"font fallback patch {patchIndex} has invalid target metadata");
        if (patch.ExistingRefs is null || patch.AppendRefs is null || patch.AppendRefs.Count == 0)
            throw new InvalidDataException($"font fallback patch {patchIndex} must define existing_refs and at least one append_ref");
        return patch;
    }

    private static FontSettingPatchSpec LoadFontSettingPatch(string specPath, int patchIndex)
    {
        string json = File.ReadAllText(specPath, Encoding.UTF8);
        FontFallbackPatchDocument? document = JsonSerializer.Deserialize<FontFallbackPatchDocument>(json, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        });
        if (document?.SettingPatches is null)
            throw new InvalidDataException("font patch spec is missing setting_patches");
        if (patchIndex >= document.SettingPatches.Count)
            throw new ArgumentOutOfRangeException(nameof(patchIndex), $"patch index {patchIndex} is outside setting_patches count {document.SettingPatches.Count}");

        FontSettingPatchSpec patch = document.SettingPatches[patchIndex];
        if (!string.Equals(patch.Field, "m_IsMultiAtlasTexturesEnabled", StringComparison.Ordinal))
            throw new InvalidDataException($"unsupported FontAsset setting field '{patch.Field}'");
        if (!string.Equals(patch.FieldType, "bool", StringComparison.Ordinal))
            throw new InvalidDataException($"unsupported FontAsset setting type '{patch.FieldType}'");
        if (patch.PathId <= 0 || string.IsNullOrWhiteSpace(patch.ObjectName) || patch.FieldOffset < 0 || patch.FieldOffset % 4 != 0)
            throw new InvalidDataException($"font setting patch {patchIndex} has invalid target metadata");
        if (patch.ScriptFileId <= 0 || patch.ScriptPathId <= 0)
            throw new InvalidDataException($"font setting patch {patchIndex} must pin the TMP_FontAsset script identity");
        if (patch.OriginalObjectSize <= 0 || patch.OriginalObjectSha256.Length != 64)
            throw new InvalidDataException($"font setting patch {patchIndex} must pin the original object size and SHA256");
        if (patch.Original is < 0 or > 1 || patch.Patched is < 0 or > 1)
            throw new InvalidDataException($"font setting patch {patchIndex} bool values must be 0 or 1");
        if (patch.Original == patch.Patched)
            throw new InvalidDataException($"font setting patch {patchIndex} does not change the setting value");
        if (patch.NeighborGuards is null || patch.NeighborGuards.Count == 0)
            throw new InvalidDataException($"font setting patch {patchIndex} must define at least one neighbor guard");
        if (patch.NeighborGuards.Any(guard => guard.Offset < 0 || guard.Offset % 4 != 0 || guard.Offset == patch.FieldOffset))
            throw new InvalidDataException($"font setting patch {patchIndex} has an invalid neighbor guard offset");
        if (patch.NeighborGuards.Select(guard => guard.Offset).Distinct().Count() != patch.NeighborGuards.Count)
            throw new InvalidDataException($"font setting patch {patchIndex} has duplicate neighbor guard offsets");
        return patch;
    }

    private static void ValidateFontSettingIdentity(byte[] serialized, FontSettingPatchSpec patch, bool expectPatchedValue)
    {
        MonoBehaviourIdentity identity = TmpFontAssetFallbackCodec.ReadMonoBehaviourIdentity(serialized);
        if (!string.Equals(identity.Name, patch.ObjectName, StringComparison.Ordinal))
            throw new InvalidDataException($"MonoBehaviour m_Name is '{identity.Name}', expected '{patch.ObjectName}'");
        if (identity.ScriptFileId != patch.ScriptFileId || identity.ScriptPathId != patch.ScriptPathId)
        {
            throw new InvalidDataException(
                $"MonoBehaviour script is ({identity.ScriptFileId},{identity.ScriptPathId}), " +
                $"expected TMP_FontAsset script ({patch.ScriptFileId},{patch.ScriptPathId})");
        }

        if (serialized.Length != patch.OriginalObjectSize)
            throw new InvalidDataException($"FontAsset serialized size is {serialized.Length}, expected {patch.OriginalObjectSize}");
        if (!expectPatchedValue)
        {
            string actualSha = Sha256(serialized);
            if (!string.Equals(actualSha, patch.OriginalObjectSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"FontAsset original object SHA256 is {actualSha}, expected {patch.OriginalObjectSha256}");
        }

        int expectedValue = expectPatchedValue ? patch.Patched : patch.Original;
        TmpFontAssetSettingCodec.ValidateAlignedBool(serialized, patch.FieldOffset, expectedValue, patch.Field);
        foreach (FontSettingGuardSpec guard in patch.NeighborGuards)
            TmpFontAssetSettingCodec.ValidateInt32(serialized, guard.Offset, guard.Value, guard.Field);
    }

    private static void ValidateFallbackTargets(AssetContext context, byte[] sourceObject, FontFallbackPatchSpec patch)
    {
        MonoBehaviourIdentity sourceIdentity = TmpFontAssetFallbackCodec.ReadMonoBehaviourIdentity(sourceObject);
        foreach (FontFallbackRefSpec reference in patch.AppendRefs)
        {
            if (reference.FileId != 0)
                throw new InvalidDataException($"only same-file fallback references are supported; got fileID {reference.FileId} for PathID {reference.PathId}");
            AssetFileInfo targetInfo = context.GetInfo(reference.PathId) ?? throw new KeyNotFoundException($"fallback target PathID {reference.PathId} was not found");
            if (targetInfo.TypeId != MonoBehaviourClassId)
                throw new InvalidDataException($"fallback target PathID {reference.PathId} has class ID {targetInfo.TypeId}, expected MonoBehaviour ({MonoBehaviourClassId})");
            byte[] targetBytes = context.ReadSerializedBytes(targetInfo);
            MonoBehaviourIdentity targetIdentity = TmpFontAssetFallbackCodec.ReadMonoBehaviourIdentity(targetBytes);
            if (!string.Equals(targetIdentity.Name, reference.Name, StringComparison.Ordinal))
                throw new InvalidDataException($"fallback target PathID {reference.PathId} name is '{targetIdentity.Name}', expected '{reference.Name}'");
            if (targetIdentity.ScriptFileId != sourceIdentity.ScriptFileId || targetIdentity.ScriptPathId != sourceIdentity.ScriptPathId)
                throw new InvalidDataException($"fallback target PathID {reference.PathId} does not use the same TMP_FontAsset MonoBehaviour script as source PathID {patch.PathId}");
        }
    }

    private static string FormatRefs(IEnumerable<FontFallbackRefSpec> refs) =>
        string.Join(", ", refs.Select(reference => $"({reference.FileId},{reference.PathId}:{reference.Name})"));

    private static void PrintRecord(string input, TextAssetRecord record, int previewBytes)
    {
        byte[] preview = record.ScriptBytes[..Math.Min(record.ScriptBytes.Length, previewBytes)];
        string previewText = Encoding.UTF8.GetString(preview)
            .Replace("\r", "\\r", StringComparison.Ordinal)
            .Replace("\n", "\\n", StringComparison.Ordinal);

        Console.WriteLine($"file:   {Path.GetFullPath(input)}");
        Console.WriteLine($"pathId: {record.PathId}");
        Console.WriteLine($"name:   {record.Name}");
        Console.WriteLine($"bytes:  {record.ScriptBytes.Length}");
        Console.WriteLine($"sha256: {Convert.ToHexString(SHA256.HashData(record.ScriptBytes)).ToLowerInvariant()}");
        Console.WriteLine($"preview-utf8: {previewText}");
    }

    private static TextAssetRecord? TryReadTextAsset(
        AssetContext context,
        long pathId,
        string label,
        List<string> failures)
    {
        AssetFileInfo? info = context.GetInfo(pathId);
        if (info is null)
        {
            failures.Add($"{label} PathID {pathId} is missing");
            return null;
        }

        if (info.TypeId != TextAssetClassId)
        {
            failures.Add($"{label} PathID {pathId} has class ID {info.TypeId}, expected TextAsset ({TextAssetClassId})");
            return null;
        }

        try
        {
            return context.ReadTextAsset(info);
        }
        catch (Exception ex) when (ex is InvalidDataException or DecoderFallbackException)
        {
            failures.Add($"{label} PathID {pathId} could not be decoded as TextAsset: {ex.Message}");
            return null;
        }
    }

    private static int VerifyLocalizationInventory(AssetContext context, string label, List<string> failures)
    {
        int validCount = 0;
        foreach ((long pathId, string expectedName) in KnownLocalizationTextAssets)
        {
            TextAssetRecord? record = TryReadTextAsset(context, pathId, $"{label} localization TextAsset", failures);
            if (record is null)
                continue;

            if (!string.Equals(record.Name, expectedName, StringComparison.Ordinal))
                failures.Add($"{label} PathID {pathId} name is '{record.Name}', expected '{expectedName}'");
            else
                validCount++;
        }
        return validCount;
    }

    private static void VerifyConfiguration(AssetContext original, AssetContext patched, List<string> failures)
    {
        AssetFileInfo? originalInfo = original.GetInfo(LocalisationConfigurationPathId);
        AssetFileInfo? patchedInfo = patched.GetInfo(LocalisationConfigurationPathId);

        if (originalInfo is null)
            failures.Add($"original LocalisationConfiguration PathID {LocalisationConfigurationPathId} is missing");
        if (patchedInfo is null)
            failures.Add($"patched LocalisationConfiguration PathID {LocalisationConfigurationPathId} is missing");
        if (originalInfo is null || patchedInfo is null)
            return;

        if (originalInfo.TypeId != MonoBehaviourClassId)
            failures.Add($"original LocalisationConfiguration PathID {LocalisationConfigurationPathId} has class ID {originalInfo.TypeId}, expected MonoBehaviour ({MonoBehaviourClassId})");
        if (patchedInfo.TypeId != originalInfo.TypeId)
            failures.Add($"patched LocalisationConfiguration PathID {LocalisationConfigurationPathId} class ID changed from {originalInfo.TypeId} to {patchedInfo.TypeId}");
        if (patchedInfo.ByteSize != originalInfo.ByteSize)
            failures.Add($"patched LocalisationConfiguration PathID {LocalisationConfigurationPathId} serialized size changed from {originalInfo.ByteSize} to {patchedInfo.ByteSize}");
    }

    private static MetadataComparison CompareMetadata(
        AssetContext original,
        AssetContext patched,
        long targetPathId,
        List<string> failures)
    {
        Dictionary<long, AssetMetadataRecord> originalMetadata = original.CaptureMetadata();
        Dictionary<long, AssetMetadataRecord> patchedMetadata = patched.CaptureMetadata();

        if (originalMetadata.Count != patchedMetadata.Count)
            failures.Add($"asset count changed from {originalMetadata.Count} to {patchedMetadata.Count}");

        foreach (long missing in originalMetadata.Keys.Except(patchedMetadata.Keys).Order())
            failures.Add($"asset PathID {missing} is missing from patched file");
        foreach (long added in patchedMetadata.Keys.Except(originalMetadata.Keys).Order())
            failures.Add($"unexpected asset PathID {added} was added to patched file");

        if (!originalMetadata.TryGetValue(targetPathId, out AssetMetadataRecord? originalTarget) ||
            !patchedMetadata.TryGetValue(targetPathId, out AssetMetadataRecord? patchedTarget))
        {
            return new MetadataComparison(originalMetadata.Count, patchedMetadata.Count, 0, 0);
        }

        long targetOffset = originalTarget.ByteOffset;
        bool targetHasFollowingAsset = originalMetadata.Values.Any(asset =>
            asset.PathId != targetPathId && asset.ByteOffset > targetOffset);
        long expectedShift = targetHasFollowingAsset
            ? Align8(patchedTarget.ByteSize) - Align8(originalTarget.ByteSize)
            : patchedTarget.ByteSize - originalTarget.ByteSize;
        int offsetChanges = 0;

        foreach ((long pathId, AssetMetadataRecord before) in originalMetadata.OrderBy(kvp => kvp.Key))
        {
            if (!patchedMetadata.TryGetValue(pathId, out AssetMetadataRecord? after))
                continue;

            if (before.TypeId != after.TypeId ||
                before.TypeIdOrIndex != after.TypeIdOrIndex ||
                before.ScriptIndex != after.ScriptIndex ||
                before.Stripped != after.Stripped)
            {
                failures.Add(
                    $"PathID {pathId} identity metadata changed " +
                    $"(type {before.TypeId}->{after.TypeId}, typeIndex {before.TypeIdOrIndex}->{after.TypeIdOrIndex}, " +
                    $"scriptIndex {before.ScriptIndex}->{after.ScriptIndex}, stripped {before.Stripped}->{after.Stripped})");
            }

            if (pathId != targetPathId && before.ByteSize != after.ByteSize)
                failures.Add($"non-target PathID {pathId} serialized size changed from {before.ByteSize} to {after.ByteSize}");

            if (pathId == targetPathId)
            {
                if (after.ByteOffset != before.ByteOffset)
                    failures.Add($"target PathID {pathId} offset changed unexpectedly from {before.ByteOffset} to {after.ByteOffset}");
                continue;
            }

            if (after.ByteOffset != before.ByteOffset)
                offsetChanges++;

            long expectedOffset = before.ByteOffset > targetOffset
                ? checked(before.ByteOffset + expectedShift)
                : before.ByteOffset;

            if (after.ByteOffset != expectedOffset)
            {
                failures.Add(
                    $"non-target PathID {pathId} offset changed unexpectedly from {before.ByteOffset} to {after.ByteOffset}; " +
                    $"expected {expectedOffset}");
            }
        }

        if (original.File.Header.MetadataSize != patched.File.Header.MetadataSize)
            failures.Add($"metadata block size changed from {original.File.Header.MetadataSize} to {patched.File.Header.MetadataSize}");
        if (original.File.Header.DataOffset != patched.File.Header.DataOffset)
            failures.Add($"data offset changed from {original.File.Header.DataOffset} to {patched.File.Header.DataOffset}");
        long expectedFileSize = checked(original.File.Header.FileSize + expectedShift);
        if (patched.File.Header.FileSize != expectedFileSize)
            failures.Add($"file size changed unexpectedly from {original.File.Header.FileSize} to {patched.File.Header.FileSize}; expected {expectedFileSize}");
        if (!string.Equals(original.File.Metadata.UnityVersion, patched.File.Metadata.UnityVersion, StringComparison.Ordinal))
            failures.Add($"Unity version metadata changed from '{original.File.Metadata.UnityVersion}' to '{patched.File.Metadata.UnityVersion}'");
        if (original.File.Metadata.TargetPlatform != patched.File.Metadata.TargetPlatform)
            failures.Add($"target platform metadata changed from {original.File.Metadata.TargetPlatform} to {patched.File.Metadata.TargetPlatform}");
        if (original.File.Metadata.TypeTreeEnabled != patched.File.Metadata.TypeTreeEnabled)
            failures.Add($"type tree enabled flag changed from {original.File.Metadata.TypeTreeEnabled} to {patched.File.Metadata.TypeTreeEnabled}");

        return new MetadataComparison(originalMetadata.Count, patchedMetadata.Count, offsetChanges, expectedShift);
    }

    private static int TryCountLocalizationRows(byte[] payload, string label, List<string> failures)
    {
        try
        {
            string text = new UTF8Encoding(false, true).GetString(payload);
            for (int i = 0; i < text.Length; i++)
            {
                if (text[i] == '\r' && (i + 1 >= text.Length || text[i + 1] != '\n'))
                    throw new InvalidDataException("contains a lone CR line ending");
            }

            string normalized = text.Replace("\r\n", "\n", StringComparison.Ordinal);
            string[] rows = normalized.Split('\n');
            return normalized.EndsWith('\n') ? rows.Length - 1 : rows.Length;
        }
        catch (Exception ex) when (ex is DecoderFallbackException or InvalidDataException)
        {
            failures.Add($"{label} is not valid line-oriented UTF-8 localization data: {ex.Message}");
            return -1;
        }
    }

    private static string Sha256(byte[] data) =>
        Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();

    private static long Align8(long value) => checked((value + 7L) & ~7L);

    private static AssetSelector ParseSelector(Dictionary<string, string?> options)
    {
        bool hasPathId = options.TryGetValue("--path-id", out string? pathIdValue);
        bool hasName = options.TryGetValue("--name", out string? nameValue);
        if (hasPathId == hasName)
            throw new ArgumentException("Specify exactly one of --path-id or --name.");

        if (hasPathId)
        {
            if (!long.TryParse(pathIdValue, out long pathId))
                throw new ArgumentException($"Invalid --path-id: {pathIdValue}");
            return new AssetSelector(pathId, null);
        }

        if (string.IsNullOrWhiteSpace(nameValue))
            throw new ArgumentException("--name must not be empty.");
        return new AssetSelector(null, nameValue);
    }

    private static Dictionary<string, string?> ParseOptions(string[] args)
    {
        var options = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        for (int i = 0; i < args.Length; i++)
        {
            string key = args[i];
            if (!key.StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException($"Unexpected argument: {key}");
            if (i + 1 >= args.Length || args[i + 1].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException($"Missing value for {key}");
            if (!options.TryAdd(key, args[++i]))
                throw new ArgumentException($"Duplicate option: {key}");
        }
        return options;
    }

    private static string RequireValue(Dictionary<string, string?> options, string key)
    {
        if (!options.TryGetValue(key, out string? value) || string.IsNullOrWhiteSpace(value))
            throw new ArgumentException($"Missing required option: {key}");
        return value;
    }

    private static string? GetOptionalValue(Dictionary<string, string?> options, string key)
    {
        if (!options.TryGetValue(key, out string? value))
            return null;
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException($"{key} must not be empty.");
        return value;
    }

    private static string RequirePath(Dictionary<string, string?> options, string key)
    {
        string path = RequireValue(options, key);
        if (!File.Exists(path))
            throw new FileNotFoundException($"File not found for {key}", path);
        return path;
    }

    private static int ParsePositiveInt(Dictionary<string, string?> options, string key, int fallback)
    {
        if (!options.TryGetValue(key, out string? value))
            return fallback;
        if (!int.TryParse(value, out int parsed) || parsed < 0)
            throw new ArgumentException($"{key} must be a non-negative integer.");
        return parsed;
    }

    private static int? ParseOptionalNonNegativeInt(Dictionary<string, string?> options, string key)
    {
        string? raw = GetOptionalValue(options, key);
        if (raw is null)
            return null;
        if (!int.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsed) || parsed < 0)
            throw new ArgumentException($"{key} must be a non-negative integer");
        return parsed;
    }

    private static long ParseLong(Dictionary<string, string?> options, string key, long fallback)
    {
        if (!options.TryGetValue(key, out string? value))
            return fallback;
        if (!long.TryParse(value, out long parsed))
            throw new ArgumentException($"{key} must be an integer.");
        return parsed;
    }

    private static long ParseRequiredLong(Dictionary<string, string?> options, string key)
    {
        string value = RequireValue(options, key);
        if (!long.TryParse(value, out long parsed))
            throw new ArgumentException($"{key} must be an integer.");
        return parsed;
    }

    private static bool IsHelp(string value) => value is "-h" or "--help" or "help";

    private static int Fail(string message)
    {
        Console.Error.WriteLine(message);
        PrintUsage();
        return 2;
    }

    private static void PrintUsage()
    {
        Console.WriteLine("BapAssetTool - inspect, safely replace, and verify Unity TextAsset m_Script payloads");
        Console.WriteLine();
        Console.WriteLine("Inspect by PathID:");
        Console.WriteLine("  dotnet run -- inspect --input sharedassets0.assets --path-id 2928");
        Console.WriteLine();
        Console.WriteLine("Inspect by m_Name:");
        Console.WriteLine("  dotnet run -- inspect --input sharedassets0.assets --name turkish");
        Console.WriteLine();
        Console.WriteLine("Replace into a NEW assets file and verify by reopening:");
        Console.WriteLine("  dotnet run -- replace --input sharedassets0.assets --output build\\sharedassets0.ko.assets --path-id 2928 --payload translations\\ko.bytes");
        Console.WriteLine();
        Console.WriteLine("Verify localization inventory and original-vs-patched asset metadata:");
        Console.WriteLine("  dotnet run -- verify --original build\\sharedassets0.original.assets --patched build\\sharedassets0.ko.assets --payload translations\\ko.bytes");
        Console.WriteLine();
        Console.WriteLine("Replace exactly one Unity serialized string field in a NEW assets file:");
        Console.WriteLine("  dotnet run -- replace-string --input in.assets --output out.assets --path-id 120642 --old #Training --new GAME_MODE_TYPE_TRAINING");
        Console.WriteLine();
        Console.WriteLine("Verify that exact serialized string-field replacement and metadata shift:");
        Console.WriteLine("  dotnet run -- verify-string --original in.assets --patched out.assets --path-id 120642 --old #Training --new GAME_MODE_TYPE_TRAINING");
        Console.WriteLine();
        Console.WriteLine("Append a validated TMP FontAsset fallback reference from a JSON patch spec:");
        Console.WriteLine("  dotnet run -- patch-font-fallback --input in.assets --output out.assets --spec config\font_fallback_patches.json --patch-index 0");
        Console.WriteLine();
        Console.WriteLine("Verify that exact TMP FontAsset fallback-table append:");
        Console.WriteLine("  dotnet run -- verify-font-fallback --original in.assets --patched out.assets --spec config\font_fallback_patches.json --patch-index 0");
        Console.WriteLine();
        Console.WriteLine("Patch one validated TMP FontAsset scalar setting from a JSON patch spec:");
        Console.WriteLine("  dotnet run -- patch-font-setting --input in.assets --output out.assets --spec config\font_fallback_patches.json --patch-index 0");
        Console.WriteLine();
        Console.WriteLine("Verify that exact TMP FontAsset scalar setting replacement:");
        Console.WriteLine("  dotnet run -- verify-font-setting --original in.assets --patched out.assets --spec config\font_fallback_patches.json --patch-index 0");
    }

    private sealed class AssetContext : IDisposable
    {
        private readonly AssetsManager manager;
        public AssetsFile File { get; }

        private AssetContext(AssetsManager manager, AssetsFile file)
        {
            this.manager = manager;
            File = file;
        }

        public static AssetContext Open(string path)
        {
            var manager = new AssetsManager();
            AssetsFileInstance instance = manager.LoadAssetsFile(path, false);
            return new AssetContext(manager, instance.file);
        }

        public TextAssetRecord Find(AssetSelector selector)
        {
            if (selector.PathId is long pathId)
            {
                AssetFileInfo? info = File.GetAssetInfo(pathId);
                if (info is null)
                    throw new KeyNotFoundException($"PathID {pathId} was not found.");
                EnsureTextAsset(info);
                return ReadRecord(info);
            }

            string wantedName = selector.Name!;
            List<TextAssetRecord> matches = new();
            foreach (AssetFileInfo info in File.Metadata.AssetInfos)
            {
                if (info.TypeId != TextAssetClassId)
                    continue;

                TextAssetRecord record;
                try
                {
                    record = ReadRecord(info);
                }
                catch (InvalidDataException)
                {
                    continue;
                }

                if (string.Equals(record.Name, wantedName, StringComparison.OrdinalIgnoreCase))
                    matches.Add(record);
            }

            return matches.Count switch
            {
                0 => throw new KeyNotFoundException($"TextAsset named '{wantedName}' was not found."),
                1 => matches[0],
                _ => throw new InvalidOperationException($"TextAsset name '{wantedName}' is ambiguous ({matches.Count} matches). Use --path-id.")
            };
        }

        public AssetFileInfo? GetInfo(long pathId) => File.GetAssetInfo(pathId);

        public TextAssetRecord ReadTextAsset(AssetFileInfo info)
        {
            EnsureTextAsset(info);
            return ReadRecord(info);
        }

        public byte[] ReadSerializedBytes(AssetFileInfo info)
        {
            if (info.ByteSize > int.MaxValue)
                throw new InvalidDataException($"Asset {info.PathId} is too large to inspect.");

            byte[] serialized = new byte[(int)info.ByteSize];
            lock (File.Reader)
            {
                File.Reader.Position = info.GetAbsoluteByteOffset(File);
                File.Reader.BaseStream.ReadExactly(serialized);
            }
            return serialized;
        }

        public Dictionary<long, AssetMetadataRecord> CaptureMetadata()
        {
            var result = new Dictionary<long, AssetMetadataRecord>(File.Metadata.AssetInfos.Count);
            foreach (AssetFileInfo info in File.Metadata.AssetInfos)
            {
                if (!result.TryAdd(
                    info.PathId,
                    new AssetMetadataRecord(
                        info.PathId,
                        info.TypeId,
                        info.TypeIdOrIndex,
                        info.GetScriptIndex(File),
                        info.Stripped,
                        info.ByteOffset,
                        info.ByteSize)))
                {
                    throw new InvalidDataException($"Duplicate PathID {info.PathId} in asset metadata.");
                }
            }
            return result;
        }

        private TextAssetRecord ReadRecord(AssetFileInfo info)
        {
            byte[] serialized = ReadSerializedBytes(info);

            TextAssetData data = TextAssetCodec.Decode(serialized);
            return new TextAssetRecord(info, info.PathId, data.Name, data.ScriptBytes, serialized);
        }

        private static void EnsureTextAsset(AssetFileInfo info)
        {
            if (info.TypeId != TextAssetClassId)
                throw new InvalidDataException($"PathID {info.PathId} has class ID {info.TypeId}, expected TextAsset ({TextAssetClassId}).");
        }

        public void Dispose() => manager.UnloadAll();
    }

    private static class TextAssetCodec
    {
        public static TextAssetData Decode(byte[] serialized)
        {
            int cursor = 0;
            byte[] nameBytes = ReadSizedBytes(serialized, ref cursor, "m_Name");
            Align4(ref cursor, serialized.Length, "m_Name");
            byte[] scriptBytes = ReadSizedBytes(serialized, ref cursor, "m_Script");
            int scriptEnd = cursor;
            Align4(ref cursor, serialized.Length, "m_Script");

            string name;
            try
            {
                name = new UTF8Encoding(false, true).GetString(nameBytes);
            }
            catch (DecoderFallbackException ex)
            {
                throw new InvalidDataException("TextAsset m_Name is not valid UTF-8.", ex);
            }

            return new TextAssetData(name, scriptBytes, scriptEnd, cursor);
        }

        public static byte[] ReplaceScript(byte[] serialized, byte[] replacement)
        {
            TextAssetData decoded = Decode(serialized);

            int scriptLengthOffset = FindScriptLengthOffset(serialized);
            int scriptDataOffset = scriptLengthOffset + sizeof(int);
            int oldAlignedEnd = decoded.AlignedEndOffset;
            int newScriptEnd = checked(scriptDataOffset + replacement.Length);
            int newAlignedEnd = Align4(newScriptEnd);
            int suffixLength = serialized.Length - oldAlignedEnd;
            byte[] rebuilt = new byte[checked(newAlignedEnd + suffixLength)];

            serialized.AsSpan(0, scriptLengthOffset).CopyTo(rebuilt);
            BinaryPrimitives.WriteInt32LittleEndian(rebuilt.AsSpan(scriptLengthOffset, sizeof(int)), replacement.Length);
            replacement.CopyTo(rebuilt.AsSpan(scriptDataOffset));
            serialized.AsSpan(oldAlignedEnd, suffixLength).CopyTo(rebuilt.AsSpan(newAlignedEnd));
            return rebuilt;
        }

        private static int FindScriptLengthOffset(byte[] serialized)
        {
            int cursor = 0;
            _ = ReadSizedBytes(serialized, ref cursor, "m_Name");
            Align4(ref cursor, serialized.Length, "m_Name");
            return cursor;
        }

        private static byte[] ReadSizedBytes(byte[] data, ref int cursor, string fieldName)
        {
            if (cursor < 0 || data.Length - cursor < sizeof(int))
                throw new InvalidDataException($"TextAsset is truncated before {fieldName} length.");

            int length = BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(cursor, sizeof(int)));
            cursor += sizeof(int);
            if (length < 0 || length > data.Length - cursor)
                throw new InvalidDataException($"TextAsset {fieldName} length is invalid: {length}.");

            byte[] value = data.AsSpan(cursor, length).ToArray();
            cursor += length;
            return value;
        }

        private static void Align4(ref int cursor, int totalLength, string fieldName)
        {
            cursor = Align4(cursor);
            if (cursor > totalLength)
                throw new InvalidDataException($"TextAsset is truncated after aligned {fieldName} data.");
        }

        private static int Align4(int value) => checked((value + 3) & ~3);
    }

    private static class SerializedStringCodec
    {
        public static byte[] ReplaceUnique(byte[] serialized, string oldValue, string newValue, out int lengthOffset)
        {
            if (string.Equals(oldValue, newValue, StringComparison.Ordinal))
                throw new ArgumentException("old and new serialized string values must differ");

            byte[] oldBytes = Encoding.UTF8.GetBytes(oldValue);
            byte[] newBytes = Encoding.UTF8.GetBytes(newValue);
            var candidates = new List<int>();

            for (int offset = 0; offset <= serialized.Length - sizeof(int); offset += 4)
            {
                int length = BinaryPrimitives.ReadInt32LittleEndian(serialized.AsSpan(offset, sizeof(int)));
                if (length != oldBytes.Length)
                    continue;

                int dataOffset = checked(offset + sizeof(int));
                int dataEnd = checked(dataOffset + length);
                if (dataEnd > serialized.Length)
                    continue;
                if (!serialized.AsSpan(dataOffset, length).SequenceEqual(oldBytes))
                    continue;

                int alignedEnd = Align4(dataEnd);
                if (alignedEnd > serialized.Length)
                    continue;
                bool paddingIsZero = true;
                for (int i = dataEnd; i < alignedEnd; i++)
                {
                    if (serialized[i] != 0)
                    {
                        paddingIsZero = false;
                        break;
                    }
                }
                if (paddingIsZero)
                    candidates.Add(offset);
            }

            if (candidates.Count != 1)
                throw new InvalidDataException($"expected exactly one aligned serialized string field with value '{oldValue}', found {candidates.Count}");

            lengthOffset = candidates[0];
            int oldDataOffset = checked(lengthOffset + sizeof(int));
            int oldDataEnd = checked(oldDataOffset + oldBytes.Length);
            int oldAlignedEnd = Align4(oldDataEnd);
            int newDataOffset = oldDataOffset;
            int newDataEnd = checked(newDataOffset + newBytes.Length);
            int newAlignedEnd = Align4(newDataEnd);
            int suffixLength = serialized.Length - oldAlignedEnd;
            byte[] rebuilt = new byte[checked(newAlignedEnd + suffixLength)];

            serialized.AsSpan(0, lengthOffset).CopyTo(rebuilt);
            BinaryPrimitives.WriteInt32LittleEndian(rebuilt.AsSpan(lengthOffset, sizeof(int)), newBytes.Length);
            newBytes.CopyTo(rebuilt.AsSpan(newDataOffset));
            serialized.AsSpan(oldAlignedEnd, suffixLength).CopyTo(rebuilt.AsSpan(newAlignedEnd));
            return rebuilt;
        }

        public static byte[] ReplaceAt(byte[] serialized, string oldValue, string newValue, int lengthOffset, out int actualLengthOffset)
        {
            if (string.Equals(oldValue, newValue, StringComparison.Ordinal))
                throw new ArgumentException("old and new serialized string values must differ");
            if (lengthOffset < 0 || lengthOffset % 4 != 0 || lengthOffset > serialized.Length - sizeof(int))
                throw new InvalidDataException($"serialized string length offset {lengthOffset} is invalid");

            byte[] oldBytes = Encoding.UTF8.GetBytes(oldValue);
            byte[] newBytes = Encoding.UTF8.GetBytes(newValue);
            int actualLength = BinaryPrimitives.ReadInt32LittleEndian(serialized.AsSpan(lengthOffset, sizeof(int)));
            if (actualLength != oldBytes.Length)
                throw new InvalidDataException($"serialized string at offset {lengthOffset} has length {actualLength}, expected {oldBytes.Length}");

            int dataOffset = checked(lengthOffset + sizeof(int));
            int oldDataEnd = checked(dataOffset + oldBytes.Length);
            if (oldDataEnd > serialized.Length || !serialized.AsSpan(dataOffset, oldBytes.Length).SequenceEqual(oldBytes))
                throw new InvalidDataException($"serialized string at offset {lengthOffset} is not '{oldValue}'");
            int oldAlignedEnd = Align4(oldDataEnd);
            if (oldAlignedEnd > serialized.Length || serialized.AsSpan(oldDataEnd, oldAlignedEnd - oldDataEnd).IndexOfAnyExcept((byte)0) >= 0)
                throw new InvalidDataException($"serialized string padding at offset {lengthOffset} is invalid");

            int newDataEnd = checked(dataOffset + newBytes.Length);
            int newAlignedEnd = Align4(newDataEnd);
            int suffixLength = serialized.Length - oldAlignedEnd;
            byte[] rebuilt = new byte[checked(newAlignedEnd + suffixLength)];
            serialized.AsSpan(0, lengthOffset).CopyTo(rebuilt);
            BinaryPrimitives.WriteInt32LittleEndian(rebuilt.AsSpan(lengthOffset, sizeof(int)), newBytes.Length);
            newBytes.CopyTo(rebuilt.AsSpan(dataOffset));
            serialized.AsSpan(oldAlignedEnd, suffixLength).CopyTo(rebuilt.AsSpan(newAlignedEnd));
            actualLengthOffset = lengthOffset;
            return rebuilt;
        }

        private static int Align4(int value) => checked((value + 3) & ~3);
    }

    private static class TmpFontAssetFallbackCodec
    {
        private const int MonoBehaviourNameLengthOffset = 28;
        private const int MonoBehaviourScriptFileIdOffset = 16;
        private const int MonoBehaviourScriptPathIdOffset = 20;
        private const int PPtrSize = 12;

        public static void ValidateFontAssetIdentity(byte[] serialized, string expectedName)
        {
            MonoBehaviourIdentity identity = ReadMonoBehaviourIdentity(serialized);
            if (!string.Equals(identity.Name, expectedName, StringComparison.Ordinal))
                throw new InvalidDataException($"MonoBehaviour m_Name is '{identity.Name}', expected '{expectedName}'");
        }

        public static MonoBehaviourIdentity ReadMonoBehaviourIdentity(byte[] serialized)
        {
            if (serialized.Length < MonoBehaviourNameLengthOffset + sizeof(int))
                throw new InvalidDataException("MonoBehaviour object is too short to contain the base header and m_Name");
            int scriptFileId = BinaryPrimitives.ReadInt32LittleEndian(serialized.AsSpan(MonoBehaviourScriptFileIdOffset, sizeof(int)));
            long scriptPathId = BinaryPrimitives.ReadInt64LittleEndian(serialized.AsSpan(MonoBehaviourScriptPathIdOffset, sizeof(long)));
            int nameLength = BinaryPrimitives.ReadInt32LittleEndian(serialized.AsSpan(MonoBehaviourNameLengthOffset, sizeof(int)));
            int nameOffset = MonoBehaviourNameLengthOffset + sizeof(int);
            if (nameLength < 0 || nameOffset + nameLength > serialized.Length)
                throw new InvalidDataException($"MonoBehaviour m_Name length is invalid: {nameLength}");
            string name;
            try
            {
                name = new UTF8Encoding(false, true).GetString(serialized, nameOffset, nameLength);
            }
            catch (DecoderFallbackException ex)
            {
                throw new InvalidDataException("MonoBehaviour m_Name is not valid UTF-8", ex);
            }
            return new MonoBehaviourIdentity(name, scriptFileId, scriptPathId);
        }

        public static byte[] AppendReferences(byte[] serialized, FontFallbackPatchSpec patch, out int fieldOffset)
        {
            fieldOffset = patch.FieldOffset;
            int existingCount = patch.ExistingRefs.Count;
            int oldVectorSize = checked(sizeof(int) + existingCount * PPtrSize);
            if (fieldOffset < 0 || fieldOffset + oldVectorSize > serialized.Length)
                throw new InvalidDataException($"{patch.Field} offset {fieldOffset} is outside serialized object bounds");

            int actualCount = BinaryPrimitives.ReadInt32LittleEndian(serialized.AsSpan(fieldOffset, sizeof(int)));
            if (actualCount != existingCount)
                throw new InvalidDataException($"{patch.Field} count at offset {fieldOffset} is {actualCount}, expected {existingCount}");

            int cursor = fieldOffset + sizeof(int);
            for (int i = 0; i < existingCount; i++)
            {
                FontFallbackRefSpec expected = patch.ExistingRefs[i];
                int actualFileId = BinaryPrimitives.ReadInt32LittleEndian(serialized.AsSpan(cursor, sizeof(int)));
                long actualPathId = BinaryPrimitives.ReadInt64LittleEndian(serialized.AsSpan(cursor + sizeof(int), sizeof(long)));
                if (actualFileId != expected.FileId || actualPathId != expected.PathId)
                {
                    throw new InvalidDataException(
                        $"{patch.Field}[{i}] at offset {cursor} is ({actualFileId},{actualPathId}), expected ({expected.FileId},{expected.PathId})");
                }
                cursor += PPtrSize;
            }

            var seen = new HashSet<(int FileId, long PathId)>(patch.ExistingRefs.Select(reference => (reference.FileId, reference.PathId)));
            foreach (FontFallbackRefSpec reference in patch.AppendRefs)
            {
                if (!seen.Add((reference.FileId, reference.PathId)))
                    throw new InvalidDataException($"duplicate fallback reference ({reference.FileId},{reference.PathId}) requested for {patch.ObjectName}");
            }

            int newCount = checked(existingCount + patch.AppendRefs.Count);
            int newVectorSize = checked(sizeof(int) + newCount * PPtrSize);
            int suffixOffset = checked(fieldOffset + oldVectorSize);
            int suffixLength = serialized.Length - suffixOffset;
            byte[] rebuilt = new byte[checked(serialized.Length + (newVectorSize - oldVectorSize))];
            serialized.AsSpan(0, fieldOffset).CopyTo(rebuilt);
            BinaryPrimitives.WriteInt32LittleEndian(rebuilt.AsSpan(fieldOffset, sizeof(int)), newCount);
            cursor = fieldOffset + sizeof(int);
            foreach (FontFallbackRefSpec reference in patch.ExistingRefs.Concat(patch.AppendRefs))
            {
                BinaryPrimitives.WriteInt32LittleEndian(rebuilt.AsSpan(cursor, sizeof(int)), reference.FileId);
                BinaryPrimitives.WriteInt64LittleEndian(rebuilt.AsSpan(cursor + sizeof(int), sizeof(long)), reference.PathId);
                cursor += PPtrSize;
            }
            serialized.AsSpan(suffixOffset, suffixLength).CopyTo(rebuilt.AsSpan(fieldOffset + newVectorSize));

            if (!rebuilt.AsSpan(0, fieldOffset).SequenceEqual(serialized.AsSpan(0, fieldOffset)))
                throw new InvalidDataException("serialized prefix changed unexpectedly while rebuilding fallback table");
            if (!rebuilt.AsSpan(fieldOffset + newVectorSize).SequenceEqual(serialized.AsSpan(suffixOffset)))
                throw new InvalidDataException("serialized suffix changed unexpectedly while rebuilding fallback table");
            return rebuilt;
        }
    }

    private static class TmpFontAssetSettingCodec
    {
        public static void ValidateAlignedBool(byte[] serialized, int offset, int expectedValue, string fieldName)
        {
            if (offset < 0 || offset + sizeof(int) > serialized.Length)
                throw new InvalidDataException($"{fieldName} offset {offset} is outside serialized object bounds");
            if (serialized[offset] != expectedValue)
                throw new InvalidDataException($"{fieldName} at offset {offset} is {serialized[offset]}, expected {expectedValue}");
            if (serialized[offset + 1] != 0 || serialized[offset + 2] != 0 || serialized[offset + 3] != 0)
                throw new InvalidDataException($"{fieldName} alignment padding at offsets {offset + 1}-{offset + 3} is not zero");
        }

        public static void ValidateInt32(byte[] serialized, int offset, int expectedValue, string fieldName)
        {
            if (offset < 0 || offset + sizeof(int) > serialized.Length)
                throw new InvalidDataException($"{fieldName} offset {offset} is outside serialized object bounds");
            int actualValue = BinaryPrimitives.ReadInt32LittleEndian(serialized.AsSpan(offset, sizeof(int)));
            if (actualValue != expectedValue)
                throw new InvalidDataException($"{fieldName} at offset {offset} is {actualValue}, expected {expectedValue}");
        }

        public static byte[] ReplaceBool(byte[] serialized, FontSettingPatchSpec patch)
        {
            ValidateAlignedBool(serialized, patch.FieldOffset, patch.Original, patch.Field);
            byte[] rebuilt = serialized.ToArray();
            rebuilt[patch.FieldOffset] = checked((byte)patch.Patched);

            if (rebuilt.Length != serialized.Length)
                throw new InvalidDataException("serialized FontAsset size changed during fixed-width setting replacement");
            if (!rebuilt.AsSpan(0, patch.FieldOffset).SequenceEqual(serialized.AsSpan(0, patch.FieldOffset)))
                throw new InvalidDataException("serialized prefix changed unexpectedly during FontAsset setting replacement");
            int suffixOffset = patch.FieldOffset + 1;
            if (!rebuilt.AsSpan(suffixOffset).SequenceEqual(serialized.AsSpan(suffixOffset)))
                throw new InvalidDataException("serialized suffix changed unexpectedly during FontAsset setting replacement");
            return rebuilt;
        }
    }

    private sealed record AssetSelector(long? PathId, string? Name);
    private sealed record TextAssetRecord(AssetFileInfo Info, long PathId, string Name, byte[] ScriptBytes, byte[] SerializedBytes);
    private sealed record TextAssetData(string Name, byte[] ScriptBytes, int ScriptEndOffset, int AlignedEndOffset);
    private sealed record AssetMetadataRecord(
        long PathId,
        int TypeId,
        int TypeIdOrIndex,
        ushort ScriptIndex,
        byte Stripped,
        long ByteOffset,
        long ByteSize);
    private sealed record MetadataComparison(
        int OriginalCount,
        int PatchedCount,
        int NonTargetOffsetChanges,
        long ExpectedOffsetShift);
    private sealed record MonoBehaviourIdentity(string Name, int ScriptFileId, long ScriptPathId);
    private sealed class SerializedStringPatchDocument
    {
        [JsonPropertyName("schema_version")]
        public int SchemaVersion { get; set; }
        [JsonPropertyName("serialized_string_patches")]
        public List<SerializedStringPatchSpec> SerializedStringPatches { get; set; } = new();
    }
    private sealed class SerializedStringPatchSpec
    {
        [JsonPropertyName("path_id")]
        public long PathId { get; set; }
        [JsonPropertyName("object_type")]
        public string ObjectType { get; set; } = "";
        [JsonPropertyName("field")]
        public string Field { get; set; } = "";
        [JsonPropertyName("original")]
        public string Original { get; set; } = "";
        [JsonPropertyName("patched")]
        public string Patched { get; set; } = "";
        [JsonPropertyName("length_offset")]
        public int? LengthOffset { get; set; }
        [JsonPropertyName("reason")]
        public string Reason { get; set; } = "";
    }
    private sealed class FontFallbackPatchDocument
    {
        [JsonPropertyName("schema_version")]
        public int SchemaVersion { get; set; }
        [JsonPropertyName("fallback_patches")]
        public List<FontFallbackPatchSpec> FallbackPatches { get; set; } = new();
        [JsonPropertyName("setting_patches")]
        public List<FontSettingPatchSpec> SettingPatches { get; set; } = new();
    }
    private sealed class FontFallbackPatchSpec
    {
        [JsonPropertyName("path_id")]
        public long PathId { get; set; }
        [JsonPropertyName("object_name")]
        public string ObjectName { get; set; } = "";
        [JsonPropertyName("field")]
        public string Field { get; set; } = "";
        [JsonPropertyName("field_offset")]
        public int FieldOffset { get; set; }
        [JsonPropertyName("existing_refs")]
        public List<FontFallbackRefSpec> ExistingRefs { get; set; } = new();
        [JsonPropertyName("append_refs")]
        public List<FontFallbackRefSpec> AppendRefs { get; set; } = new();
    }
    private sealed class FontFallbackRefSpec
    {
        [JsonPropertyName("file_id")]
        public int FileId { get; set; }
        [JsonPropertyName("path_id")]
        public long PathId { get; set; }
        [JsonPropertyName("name")]
        public string Name { get; set; } = "";
    }
    private sealed class FontSettingPatchSpec
    {
        [JsonPropertyName("path_id")]
        public long PathId { get; set; }
        [JsonPropertyName("object_name")]
        public string ObjectName { get; set; } = "";
        [JsonPropertyName("script_file_id")]
        public int ScriptFileId { get; set; }
        [JsonPropertyName("script_path_id")]
        public long ScriptPathId { get; set; }
        [JsonPropertyName("original_object_size")]
        public int OriginalObjectSize { get; set; }
        [JsonPropertyName("original_object_sha256")]
        public string OriginalObjectSha256 { get; set; } = "";
        [JsonPropertyName("field")]
        public string Field { get; set; } = "";
        [JsonPropertyName("field_type")]
        public string FieldType { get; set; } = "";
        [JsonPropertyName("field_offset")]
        public int FieldOffset { get; set; }
        [JsonPropertyName("original")]
        public int Original { get; set; }
        [JsonPropertyName("patched")]
        public int Patched { get; set; }
        [JsonPropertyName("neighbor_guards")]
        public List<FontSettingGuardSpec> NeighborGuards { get; set; } = new();
    }
    private sealed class FontSettingGuardSpec
    {
        [JsonPropertyName("field")]
        public string Field { get; set; } = "";
        [JsonPropertyName("offset")]
        public int Offset { get; set; }
        [JsonPropertyName("value")]
        public int Value { get; set; }
    }
}
