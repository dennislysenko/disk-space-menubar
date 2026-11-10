// Launcher for "Disk Space.app".
//
// macOS privacy permissions (Full Disk Access, needed to read ~/.Trash) belong to the
// "responsible" app of a process. Running the Python script as a *child* of this app
// makes the app responsible, so the permission is granted to Disk Space.app alone
// rather than to every script that uses the Homebrew Python.
import Foundation

guard let repo = Bundle.main.object(forInfoDictionaryKey: "DSRepoPath") as? String else {
    FileHandle.standardError.write("Disk Space: DSRepoPath missing from Info.plist\n".data(using: .utf8)!)
    exit(1)
}

let child = Process()
child.executableURL = URL(fileURLWithPath: repo + "/venv/bin/python")
child.arguments = [repo + "/disk_space.py"]
child.currentDirectoryURL = URL(fileURLWithPath: repo)

// Pass launchd's stop signal on to the script so it quits with us
var sources: [DispatchSourceSignal] = []
for sig in [SIGTERM, SIGINT, SIGHUP] {
    signal(sig, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler { if child.isRunning { kill(child.processIdentifier, sig) } }
    source.resume()
    sources.append(source)
}
child.terminationHandler = { exit($0.terminationStatus) }

do {
    try child.run()
} catch {
    FileHandle.standardError.write("Disk Space: couldn't start Python: \(error)\n".data(using: .utf8)!)
    exit(1)
}
dispatchMain()
