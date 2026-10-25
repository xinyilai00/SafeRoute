//
//  DriveSpeaker.swift
//  SafeRoute
//

import AVFoundation

/// Spoken drive alerts. Other audio (music, podcasts) is ducked while a phrase plays and
/// restored when it ends. Main-actor isolated like the rest of the app; the synthesizer's
/// delegate callbacks are `nonisolated` and hop back.
final class DriveSpeaker: NSObject, AVSpeechSynthesizerDelegate {
    var isMuted = false

    private let synthesizer = AVSpeechSynthesizer()
    private var isSessionActive = false

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    func speak(_ text: String) {
        guard !isMuted else { return }
        activateSession()
        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.95
        utterance.preUtteranceDelay = 0.1
        synthesizer.speak(utterance)
    }

    /// Cuts any phrase short and gives the audio back to other apps.
    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
        deactivateSession()
    }

    private func activateSession() {
        guard !isSessionActive else { return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .voicePrompt, options: [.duckOthers, .interruptSpokenAudioAndMixWithOthers])
            try session.setActive(true)
            isSessionActive = true
        } catch {
            print("DriveSpeaker: audio session unavailable, speaking anyway. \(error)")
        }
    }

    private func deactivateSession() {
        guard isSessionActive, !synthesizer.isSpeaking else { return }
        isSessionActive = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    // MARK: - AVSpeechSynthesizerDelegate

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in self.deactivateSession() }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor in self.deactivateSession() }
    }
}
