import Cocoa
import Foundation

let files = FileManager.default
let resources = Bundle.main.resourceURL!
let root = files.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/TalkingHeadStudio")
let code = root.appendingPathComponent("talking-head-studio")
let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
let silent = CommandLine.arguments.contains("--no-browser")
let logURL = files.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/TalkingHeadStudio-install.log")
struct InstallError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

@discardableResult
func run(_ executable: String, _ arguments: [String], check: Bool = true) throws -> Int32 {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    try files.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    if !files.fileExists(atPath: logURL.path) { files.createFile(atPath: logURL.path, contents: nil) }
    let log = try FileHandle(forWritingTo: logURL)
    defer { try? log.close() }
    try log.seekToEnd()
    process.standardOutput = log
    process.standardError = log
    try process.run()
    process.waitUntilExit()
    if check && process.terminationStatus != 0 { throw InstallError(message:"操作未完成。详情见 " + logURL.path) }
    return process.terminationStatus
}

func launch() throws {
    let runtime = root.appendingPathComponent("runtime/bin/python").path
    let marker = try? String(contentsOf: code.appendingPathComponent(".studio-install"), encoding:.utf8)
    if marker?.trimmingCharacters(in:.whitespacesAndNewlines) == version && files.isExecutableFile(atPath:runtime) {
        var args = ["-X","utf8",code.appendingPathComponent("scripts/launch.py").path]
        if let data = try? Data(contentsOf:code.appendingPathComponent(".studio-deployment.json")),
           let settings = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any] {
            if let path = settings["data"] as? String { args += ["--data",path] }
            if let port = settings["port"] as? Int { args += ["--port",String(port)] }
        }
        if silent { args.append("--no-browser") }
        try run(runtime,args)
        return
    }
    let official = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
    let paths = [official,"/opt/homebrew/bin/python3.12","/usr/local/bin/python3.12","/opt/homebrew/bin/python3","/usr/local/bin/python3"]
    var python = paths.first { path in
        files.isExecutableFile(atPath:path) && (try? run(path,["-c","import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)"],check:false)) == 0
    }
    if python == nil {
        if silent { throw InstallError(message:"请在 Finder 打开应用，完成随附的 Python 安装。") }
        try run("/usr/bin/open",["-W",resources.appendingPathComponent("python-3.13.14-macos11.pkg").path])
        guard files.isExecutableFile(atPath:official) else { throw InstallError(message:"Python 尚未安装。重新打开工作台即可继续。") }
        python = official
    }
    var args = ["-X","utf8",resources.appendingPathComponent("bootstrap.py").path,"--no-shortcut"]
    if silent { args.append("--no-browser") }
    try run(python!,args)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let status = NSPanel(contentRect:NSRect(x:0,y:0,width:390,height:85), styleMask:[.titled],backing:.buffered,defer:false)
status.title = "口播导演工作台"
let message = NSTextField(labelWithString:"正在打开工作台。首次安装可能需要几分钟。")
message.frame = NSRect(x:18,y:30,width:355,height:28)
status.contentView?.addSubview(message)
if !silent { status.center(); status.orderFrontRegardless() }
DispatchQueue.global(qos:.userInitiated).async {
    do { try launch(); DispatchQueue.main.async { NSApp.terminate(nil) } }
    catch { DispatchQueue.main.async {
        if silent { fputs(error.localizedDescription,stderr);exit(1) }
        status.orderOut(nil)
        let alert=NSAlert();alert.messageText="工作台暂时无法打开";alert.informativeText=error.localizedDescription
        alert.runModal();exit(1)
    } }
}
app.run()
