// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

import {ERC165} from "../oz/utils/introspection/ERC165.sol";
import {Secp256k1} from "./libraries/Secp256k1.sol";
import {SchnorrVerify} from "./libraries/SchnorrVerify.sol";
import {NestedFrames} from "./libraries/NestedFrames.sol";
import {ISchnorrStakeRegistry} from "./interface/ISchnorrStakeRegistry.sol";
import {ISchnorrApprovalRegistry, QuorumSignature} from "./interface/ISchnorrApprovalRegistry.sol";

/// @title SchnorrStakeRegistry
/// @notice Stake registry for the **aggregate Schnorr** quorum scheme — the Schnorr
///         equivalent of EigenLayer's `ECDSAStakeRegistry`. Instead of verifying `N`
///         individual signatures, it maintains a watermark-snapshotted **aggregate**
///         operator public key `X_all = Σ X_i` (a single current value, not a per-block
///         history) and verifies a single aggregate signature against
///         `X_agg = X_all − Σ non-signers` in constant gas.
///
/// @dev Mirrors the "aggressive snapshot" registry-cache design from the ECDSA gas-opt
///      work (service #311): a `_effectiveBlock` watermark records the last operator-set
///      mutation, and verification is **fail-closed** — it requires
///      `refBlock >= _effectiveBlock` so the cached aggregate/weights are guaranteed equal
///      to their historical values at `refBlock`. Plain (linear) key aggregation is safe
///      here only because registration requires a **proof of possession**, which defeats
///      rogue-key attacks (the same guarantee `BLSApkRegistry` enforces for BLS).
///
///      This is a self-contained implementation (no EigenLayer base classes) so the whole
///      verify + subtraction + threshold path is unit-testable; production would layer the
///      operator/AVS registration lifecycle on top, exactly as `ECDSAStakeRegistry` does.
///
///      **The operator set must be quiescent relative to a signing round.** Because only the
///      current aggregate is stored, every operator-set mutation invalidates any signature an
///      off-chain round has already assembled against the prior set — see `isValidSignature` for
///      the two ways that surfaces. Registration and deregistration are equally affected. The
///      cost is a retry, not a soundness risk: the failure mode is a rejected signature, never
///      acceptance of one that no current-set quorum endorsed.
///
///      `announceRegister` / `announceDeregister` exist to make that quiescence checkable rather
///      than assumed. A change announced now applies only after `noticeWindow` blocks, so
///      `nextPossibleMutationBlock()` tells an off-chain round how long the set it assembled
///      against will remain the set that verifies it. `registerOperator` and
///      `deregisterOperator` bypass the window for bootstrap and emergencies and emit
///      `ForcedMutation`; consumers should treat that event, and any
///      `OperatorRegistered` / `OperatorDeregistered` without a preceding announcement, as
///      "re-snapshot required".
///
///      A mutation also changes *what counts as* a quorum, because the threshold is measured
///      against the current `totalWeight`. Removing an operator can turn a signature holding
///      less than the threshold share of the old set into a valid quorum of the smaller one —
///      correctly, since the remaining signers do carry that share. What binds a signature to
///      one specific signer set is the aggregate match (`X_all − Σ non-signers` must equal the
///      key that signed), not the watermark: advancing `effectiveBlock` does not restrict which
///      quorums are acceptable, it guarantees the cached aggregate and weights are the ones in
///      force at `refBlock` so the registry never answers for a snapshot it no longer holds.
///
///      For nested settlement, `verifyAndApprove` runs the same verification once for a tree's
///      root and records the approval in transient storage, where every frame of the tree reads
///      it through `approvedRefBlock`. Approvals never touch persistent storage, so the slot
///      layout above is unchanged and an approval cannot outlive its transaction.
contract SchnorrStakeRegistry is ISchnorrApprovalRegistry, ERC165 {
    /// Domain tag for the proof-of-possession message — must equal the Rust `POP_TAG`.
    bytes internal constant POP_TAG = "gas-killer/schnorr/pop/v1";

    struct Operator {
        uint256 x; // pubkey x
        uint256 y; // pubkey y
        // `weight`, `registered` and `exitBlock` share a slot (96 + 8 + 48 bits): the
        // verification loop reads a non-signer's whole record, so packing saves one cold SLOAD
        // per non-signer. uint96 matches EigenLayer's stake-weight width.
        uint96 weight; // stake weight
        bool registered; // in the active set — the only field the verification loop consults
        uint48 exitBlock; // block of the operator's most recent exit; 0 if it has never exited
    }

    /// @notice operator Ethereum address (= address of its pubkey point) → operator record.
    /// @dev An exited operator's record is retained as a tombstone rather than deleted: `x`, `y`,
    ///      `weight` and `exitBlock` stay readable so the identity remains attributable after it
    ///      leaves the set, which a fraud proof settled after the exit needs. Only `registered`
    ///      governs membership, so a tombstone is inert for verification — it is not in `X_all`,
    ///      not counted in `totalWeight`, and rejected as a non-signer. Re-registration
    ///      overwrites the record wholesale, clearing `exitBlock`.
    mapping(address => Operator) public operators;

    /// A scheduled operator-set change: announced now, applicable from `eligibleBlock`.
    struct PendingChange {
        ChangeKind kind;
        uint48 eligibleBlock;
        address operator; // identity (`pointAddress(x, y)`)
        uint256 x; // register only
        uint256 y; // register only
        uint96 weight; // register only
    }

    enum ChangeKind {
        Register,
        Deregister
    }

    /// Running aggregate public key `X_all = Σ X_i` (identity = `(0,0)`).
    uint256 public aggX;
    uint256 public aggY;
    /// Total registered stake weight.
    uint256 public totalWeight;
    /// Block of the last operator-set mutation (verification fail-closes below this).
    uint256 public effectiveBlock;

    // The verification hot path reads `operators`, `aggX`, `aggY`, `totalWeight` and
    // `effectiveBlock`; they are declared first so scheduling state cannot displace them.

    /// FIFO of announced-but-unapplied changes, `[pendingHead, pendingTail)`.
    ///
    /// `eligibleBlock` is non-decreasing in announcement order, so the head is the earliest block
    /// at which the operator set can next change. Cancelling out of the middle leaves a zeroed
    /// hole; `pendingHead` is always kept on a live entry (or equal to `pendingTail`) so reading
    /// the horizon stays a single storage load. A live entry's `operator` is never the zero
    /// address — it is either `pointAddress` of a key with a verified proof of possession, or an
    /// identity that had to be `registered` to be queued for removal — so zero marks a hole
    /// unambiguously.
    mapping(uint256 => PendingChange) public pendingChanges;
    uint256 public pendingHead;
    uint256 public pendingTail;
    /// Queue position of an identity's announced change, stored one-based so that zero means
    /// "nothing queued". Keeps both the duplicate-announcement check and cancelling a specific
    /// identity's change O(1), wherever it sits in the queue.
    mapping(address => uint256) public pendingChangeIndex;
    /// Live entries in the queue. Tracked rather than derived from `pendingTail - pendingHead`,
    /// which counts the holes a mid-queue cancellation leaves behind.
    uint256 internal pendingLive;

    /// Threshold as a fraction `num/den` of total weight required to sign (e.g. 2/3).
    uint256 public immutable thresholdNum;
    uint256 public immutable thresholdDen;

    /// @notice Blocks that must pass between announcing a change and applying it.
    /// @dev Must exceed the longest window a settlement can span — the signing round's duration
    ///      plus the consumer's `blockStaleMeasure` — or a round can still be assembled under one
    ///      operator set and settled under another. That bound lives on each consumer contract
    ///      and is adjustable there, while one registry may back several consumers, so the
    ///      registry cannot check the relationship; sizing this correctly is a deployment
    ///      responsibility.
    uint256 public immutable noticeWindow;

    /// @notice The registry owner, allowed to register operators (stands in for the
    ///         EigenLayer registration lifecycle).
    address public immutable owner;

    error NotOwner();
    error AlreadyRegistered();
    error NotOnCurve();
    error InvalidProofOfPossession();
    error NotRegistered(address operator);
    error NonSignersNotSorted();
    error FutureReferenceBlock();
    error StaleSnapshot();
    error ZeroWeight();
    error WeightOverflow();
    error ChangeAlreadyPending(address operator);
    error NoPendingChange();
    error NoticeWindowNotElapsed(uint256 eligibleBlock);
    error NoticeWindowTooLarge();

    event OperatorRegistered(address indexed operator, uint256 weight);
    event OperatorDeregistered(address indexed operator, uint256 weight);
    event ChangeAnnounced(uint256 indexed index, ChangeKind kind, address indexed operator, uint256 eligibleBlock);
    event ChangeCancelled(uint256 indexed index, address indexed operator);
    /// Emitted when a change bypasses the notice window via the forced path.
    event ForcedMutation(address indexed operator);

    /// Upper bound on `noticeWindow`. Keeping both terms of `block.number + noticeWindow` under
    /// half of `uint48` means `eligibleBlock` cannot wrap when narrowed — a wrapped value would
    /// land in the past and make a change committable immediately, defeating the window. The
    /// bound is ~1.4e14 blocks, so it constrains nothing reachable.
    uint256 internal constant MAX_NOTICE_WINDOW = uint256(type(uint48).max) / 2;

    /// keccak256("gaskiller.registry.approval") - 1; a root's approval lives in transient slot
    /// `keccak256(abi.encode(APPROVAL_NAMESPACE, root))`.
    bytes32 internal constant APPROVAL_NAMESPACE = 0x46b23aa16c26504969dc09800f811911d430d166240c299f498c943297b40365;

    constructor(uint256 _thresholdNum, uint256 _thresholdDen, address _owner, uint256 _noticeWindow) {
        require(_thresholdDen != 0 && _thresholdNum <= _thresholdDen, "bad threshold");
        if (_noticeWindow > MAX_NOTICE_WINDOW) revert NoticeWindowTooLarge();
        thresholdNum = _thresholdNum;
        thresholdDen = _thresholdDen;
        owner = _owner;
        noticeWindow = _noticeWindow;
        effectiveBlock = block.number;
    }

    /// @dev Consumers report `IGasKillerNested` only while their registry reports
    ///      `ISchnorrApprovalRegistry` here, so a router never plans a tree this cannot settle.
    function supportsInterface(bytes4 interfaceId) public view virtual override returns (bool) {
        return interfaceId == type(ISchnorrApprovalRegistry).interfaceId
            || interfaceId == type(ISchnorrStakeRegistry).interfaceId || super.supportsInterface(interfaceId);
    }

    /// @dev The check is wrapped rather than inlined in the modifier body so the revert is emitted
    ///      once instead of at every call site.
    function _checkOwner() private view {
        if (msg.sender != owner) revert NotOwner();
    }

    modifier onlyOwner() {
        _checkOwner();
        _;
    }

    /// @notice The Ethereum address of a public-key point (`keccak256(x‖y)[12:]`). This is
    ///         the operator identity used to look up non-signers.
    function pointAddress(uint256 x, uint256 y) public pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encodePacked(x, y)))));
    }

    /// @notice The proof-of-possession message for an operator identity.
    function popMessage(address operator) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(POP_TAG, operator));
    }

    // ---------------------------------------------------------------------------------------
    // Scheduled operator-set changes
    //
    // Every mutation invalidates a signature already assembled against the prior set (see
    // `isValidSignature`). Announcing a change ahead of time gives an off-chain round a horizon
    // it can rely on: while `nextPossibleMutationBlock()` is beyond the block a settlement will
    // land in, the set it assembled against is still the set that will verify it. The horizon is
    // a guarantee for this path only — `forceRegisterOperator` / `forceDeregisterOperator` bypass
    // it — so the fail-closed watermark remains the backstop rather than the primary defence.
    // ---------------------------------------------------------------------------------------

    /// @notice Announce a registration, applicable once the notice window has elapsed.
    /// @dev The key is fully validated here — curve membership, weight bounds and proof of
    ///      possession — so an unusable announcement cannot sit in the queue and stall the
    ///      horizon. Nothing is added to `X_all` until the change is committed, so the announced
    ///      operator must not sign until then; its key would not be in the aggregate.
    /// @param x       pubkey x-coordinate.
    /// @param y       pubkey y-coordinate.
    /// @param weight  stake weight to credit on commit.
    /// @param popS    PoP signature scalar `s`.
    /// @param popR    PoP nonce address `address(R)`.
    /// @return index  queue position of the announced change.
    function announceRegister(uint256 x, uint256 y, uint256 weight, uint256 popS, address popR)
        external
        onlyOwner
        returns (uint256 index)
    {
        address id = _validateRegistration(x, y, weight, popS, popR);

        // casting to 'uint96' is safe: bounds-checked against type(uint96).max above
        // forge-lint: disable-next-line(unsafe-typecast)
        return _enqueue(ChangeKind.Register, id, x, y, uint96(weight));
    }

    /// @notice Announce a deregistration, applicable once the notice window has elapsed.
    /// @dev The operator stays in `X_all` and in `totalWeight` for the whole window and is
    ///      expected to keep signing. If it goes dark early the non-signer path absorbs its
    ///      absence, but its weight still counts toward the threshold denominator until the
    ///      change is committed — so announcing exits faster than the set can absorb them is a
    ///      liveness risk, not a safety one.
    /// @param operator  the operator identity (`pointAddress(x, y)`) to remove on commit.
    /// @return index    queue position of the announced change.
    function announceDeregister(address operator) external onlyOwner returns (uint256 index) {
        if (!operators[operator].registered) revert NotRegistered(operator);
        return _enqueue(ChangeKind.Deregister, operator, 0, 0, 0);
    }

    /// @notice Apply the oldest announced change once its notice window has elapsed.
    /// @dev Changes commit in announcement order. Because `eligibleBlock` is non-decreasing in
    ///      that order, the head of the queue is always the earliest possible mutation, which is
    ///      what makes `nextPossibleMutationBlock()` a single storage read rather than a scan.
    function commitNextChange() external onlyOwner {
        // Cancellation already leaves the head on a live entry, so this is a no-op in practice.
        // It runs before the head is read rather than after, so committing a cleared slot — which
        // would apply a zero-address, zero-weight change — cannot depend on that being true.
        _advancePastHoles();
        if (pendingHead == pendingTail) revert NoPendingChange();

        PendingChange memory change = pendingChanges[pendingHead];
        if (block.number < change.eligibleBlock) revert NoticeWindowNotElapsed(change.eligibleBlock);

        delete pendingChanges[pendingHead];
        delete pendingChangeIndex[change.operator];
        --pendingLive;
        ++pendingHead;
        _advancePastHoles();

        if (change.kind == ChangeKind.Register) {
            _applyRegister(change.operator, change.x, change.y, change.weight);
        } else {
            _applyDeregister(change.operator);
        }
    }

    /// @notice Drop the oldest announced change without applying it.
    /// @dev Only ever moves `nextPossibleMutationBlock()` later, never earlier, so it cannot
    ///      invalidate a round assembled against the horizon it published. Needed because an
    ///      abandoned announcement would otherwise pin the horizon and block every change behind
    ///      it in the queue.
    function cancelNextChange() external onlyOwner {
        if (pendingHead == pendingTail) revert NoPendingChange();
        _cancelAt(pendingHead);
    }

    /// @notice Drop a specific identity's announced change, wherever it sits in the queue.
    /// @dev Cancelling out of the middle leaves a hole rather than reordering, so the entries
    ///      around it keep both their positions and their `eligibleBlock`s — an unrelated
    ///      operator part-way through its notice window is not sent back to the start of it.
    ///
    ///      This is what keeps the forced paths usable: they refuse to act on an identity with a
    ///      queued change, and clearing that one entry no longer means cancelling everything
    ///      ahead of it. An emergency removal is `cancelChange(operator)` then
    ///      `deregisterOperator(operator)`, with no time gate between them.
    ///
    ///      Horizon-monotonic like `cancelNextChange`: removing a non-head entry leaves the
    ///      earliest `eligibleBlock` untouched, and removing the head can only move it later.
    /// @param operator  the identity whose announced change should be dropped.
    function cancelChange(address operator) external onlyOwner {
        uint256 oneBased = pendingChangeIndex[operator];
        if (oneBased == 0) revert NoPendingChange();
        _cancelAt(oneBased - 1);
    }

    /// @notice The earliest block at which the operator set can change, or `type(uint256).max`
    ///         when nothing is announced.
    /// @dev A settlement is safe from set-mutation invalidation while the block it lands in is
    ///      below this value. It is a bound on the *scheduled* path only; the forced path can
    ///      mutate at any block.
    function nextPossibleMutationBlock() external view returns (uint256) {
        if (pendingHead == pendingTail) return type(uint256).max;
        return pendingChanges[pendingHead].eligibleBlock;
    }

    /// @notice Number of announced changes not yet committed or cancelled.
    function pendingChangeCount() external view returns (uint256) {
        return pendingLive;
    }

    // ---------------------------------------------------------------------------------------
    // Forced operator-set changes
    // ---------------------------------------------------------------------------------------

    /// @notice Register an operator immediately, bypassing the notice window.
    /// @dev The path to use while bootstrapping a registry that does not yet back any consumer,
    ///      when there is no round to invalidate. Once the registry is live, prefer
    ///      `announceRegister`: this invalidates any signature already assembled against the
    ///      pre-registration aggregate — a newly registered key cannot contribute to a round
    ///      already under way, and its presence in `X_all` is enough to break one — and it does so
    ///      without the advance warning `announceRegister` gives, so consumers relying on
    ///      `nextPossibleMutationBlock()` will be caught out. `ForcedMutation` marks the bypass
    ///      for off-chain consumers.
    /// @param x       pubkey x-coordinate.
    /// @param y       pubkey y-coordinate.
    /// @param weight  stake weight to credit.
    /// @param popS    PoP signature scalar `s`.
    /// @param popR    PoP nonce address `address(R)`.
    function registerOperator(uint256 x, uint256 y, uint256 weight, uint256 popS, address popR) external onlyOwner {
        address id = _validateRegistration(x, y, weight, popS, popR);
        _requireNoScheduledChange(id);
        emit ForcedMutation(id);
        // casting to 'uint96' is safe: bounds-checked against type(uint96).max above
        // forge-lint: disable-next-line(unsafe-typecast)
        _applyRegister(id, x, y, uint96(weight));
    }

    /// @notice Deregister an operator immediately, bypassing the notice window.
    /// @dev The escape hatch for an operator that must leave the set at once — a compromised key
    ///      cannot wait out a notice window. Carries the same lack of advance warning as the
    ///      immediate registration path, so `announceDeregister` is the routine way to remove an
    ///      operator and this is the exception.
    /// @param operator  the operator identity (`pointAddress(x, y)`) to remove.
    function deregisterOperator(address operator) external onlyOwner {
        _requireNoScheduledChange(operator);
        emit ForcedMutation(operator);
        _applyDeregister(operator);
    }

    // ---------------------------------------------------------------------------------------
    // Mutation internals
    // ---------------------------------------------------------------------------------------

    /// @dev Shared validation for both registration paths. Reverts unless the key is on the
    ///      curve, the weight fits `uint96` and is non-zero, the identity is not already in the
    ///      active set, and the proof of possession checks out.
    function _validateRegistration(uint256 x, uint256 y, uint256 weight, uint256 popS, address popR)
        private
        view
        returns (address id)
    {
        if (weight == 0) revert ZeroWeight();
        if (weight > type(uint96).max) revert WeightOverflow();
        if (!Secp256k1.isOnCurve(x, y)) revert NotOnCurve();

        id = pointAddress(x, y);
        if (operators[id].registered) revert AlreadyRegistered();

        // Proof of possession: a single-key Schnorr signature over popMessage(id), verified
        // against this very key. Without it, plain key aggregation would be rogue-key-forgeable.
        uint8 parity = uint8(y & 1);
        if (!SchnorrVerify.verify(x, parity, popMessage(id), popS, popR)) {
            revert InvalidProofOfPossession();
        }
    }

    /// @dev Clear one queue slot and keep `pendingHead` on a live entry.
    function _cancelAt(uint256 index) private {
        address operator = pendingChanges[index].operator;

        delete pendingChanges[index];
        delete pendingChangeIndex[operator];
        --pendingLive;

        emit ChangeCancelled(index, operator);

        _advancePastHoles();
    }

    /// @dev Restore the invariant that `pendingHead` addresses a live entry, so the horizon is a
    ///      single read and `commitNextChange` never lands on a cancelled slot. The loop only ever
    ///      walks holes the owner created, and each iteration permanently retires one queue slot.
    function _advancePastHoles() private {
        uint256 head = pendingHead;
        uint256 tail = pendingTail;
        while (head < tail && pendingChanges[head].operator == address(0)) {
            ++head;
        }
        pendingHead = head;
    }

    /// @dev The forced paths refuse to act on an identity that already has a queued change, so the
    ///      scheduled and forced paths can never both apply to it.
    ///
    ///      Without this rule an announced registration could be forced through first — an
    ///      announcement leaves `registered` false, so nothing in `_validateRegistration` would
    ///      object — and the still-queued entry would then apply the same key a second time on
    ///      commit, adding it to `X_all` and `totalWeight` twice. The mirror case, forcing a
    ///      deregistration that is already announced, would instead wedge the queue: the head
    ///      would revert `NotRegistered` on every commit and, because changes commit in order,
    ///      block everything behind it until cancelled.
    ///
    ///      An identity must therefore be committed or cancelled before it can be forced. That
    ///      also keeps the queue head valid by construction, since only `_applyRegister` and
    ///      `_applyDeregister` change membership and neither can now run behind the queue's back.
    function _requireNoScheduledChange(address operator) private view {
        if (pendingChangeIndex[operator] != 0) revert ChangeAlreadyPending(operator);
    }

    /// @dev Append a change to the FIFO and mark its identity as spoken for.
    function _enqueue(ChangeKind kind, address operator, uint256 x, uint256 y, uint96 weight)
        private
        returns (uint256 index)
    {
        if (pendingChangeIndex[operator] != 0) revert ChangeAlreadyPending(operator);

        // Cannot wrap: `noticeWindow` is bounded by MAX_NOTICE_WINDOW and a block number
        // approaching the other half of uint48 (~1.4e14) is unreachable.
        // forge-lint: disable-next-line(unsafe-typecast)
        uint48 eligibleBlock = uint48(block.number + noticeWindow);

        index = pendingTail;
        pendingChangeIndex[operator] = index + 1;
        ++pendingLive;
        pendingChanges[index] =
            PendingChange({kind: kind, eligibleBlock: eligibleBlock, operator: operator, x: x, y: y, weight: weight});
        ++pendingTail;

        emit ChangeAnnounced(index, kind, operator, eligibleBlock);
    }

    /// @dev Add a validated key to the active set. Overwrites the record wholesale, which clears
    ///      any tombstone left by a previous exit.
    ///
    ///      The membership check is redundant against the callers — the forced path validates and
    ///      `_requireNoScheduledChange` keeps the queue head valid — but adding a key already in
    ///      `X_all` corrupts the aggregate irrecoverably, so the invariant is asserted where it is
    ///      relied on rather than only where it is currently established. `_applyDeregister`
    ///      carries the same check in the opposite direction.
    function _applyRegister(address id, uint256 x, uint256 y, uint96 weight) private {
        if (operators[id].registered) revert AlreadyRegistered();
        operators[id] = Operator({x: x, y: y, weight: weight, registered: true, exitBlock: 0});
        (aggX, aggY) = Secp256k1.add(aggX, aggY, x, y);
        totalWeight += weight;
        effectiveBlock = block.number;

        emit OperatorRegistered(id, weight);
    }

    /// @dev Remove an operator from the active set, leaving a tombstone behind. Subtracting the
    ///      key must read `op.x`/`op.y` before `registered` is cleared; the record is retained
    ///      rather than deleted so the identity stays attributable after the exit.
    function _applyDeregister(address operator) private {
        Operator storage op = operators[operator];
        if (!op.registered) revert NotRegistered(operator);

        uint256 weight = op.weight;
        (aggX, aggY) = Secp256k1.sub(aggX, aggY, op.x, op.y);
        totalWeight -= weight;
        effectiveBlock = block.number;

        op.registered = false;
        // A block number exceeding uint48 is unreachable (~2.8e14 blocks).
        // forge-lint: disable-next-line(unsafe-typecast)
        op.exitBlock = uint48(block.number);

        emit OperatorDeregistered(operator, weight);
    }

    /// @notice Verify an aggregate Schnorr signature for `message`, accounting for the
    ///         declared non-signers.
    /// @dev An operator-set mutation between the moment a round assembles its signature and the
    ///      moment the settlement is included makes that signature unusable. Which of two
    ///      failure modes a caller observes depends on when it pins `refBlock`:
    ///
    ///      - pinned **before** the mutation → `refBlock < effectiveBlock` and this reverts
    ///        `StaleSnapshot`.
    ///      - pinned **after** the mutation (the freshest-block strategy, `block.number - 1`) →
    ///        the watermark check passes, but the cached aggregate is no longer the one the
    ///        operators signed against, so verification fails and this returns `false`.
    ///
    ///      Both require the round to be re-assembled against the current set; neither can
    ///      admit a signature that was not valid for the set at `refBlock`.
    /// @param message     the signed 32-byte task digest.
    /// @param s           aggregate response scalar.
    /// @param Raddr       aggregate nonce address `address(R)`.
    /// @param nonSigners  operator identities that did NOT sign, strictly ascending.
    /// @param refBlock    reference block; must be `>= effectiveBlock` and `< block.number`.
    /// @return ok         true iff the quorum signed and the signature verifies.
    function isValidSignature(
        bytes32 message,
        uint256 s,
        address Raddr,
        address[] calldata nonSigners,
        uint256 refBlock
    ) external view override returns (bool ok) {
        return _isValidSignature(message, s, Raddr, nonSigners, refBlock);
    }

    /// @inheritdoc ISchnorrApprovalRegistry
    /// @dev Expiry is checked here rather than by each frame, so no approval, and so no nested
    ///      frame, can exist after it whatever contract sits above that frame.
    function verifyAndApprove(
        bytes32 root,
        address rootContract,
        uint256 expiryBlock,
        bytes32[] calldata expiryProof,
        QuorumSignature calldata sig
    ) external override {
        if (block.number > expiryBlock) revert ApprovalExpired(expiryBlock);
        if (!NestedFrames.isMemberCalldata(expiryProof, root, NestedFrames.expiryLeaf(rootContract, expiryBlock))) {
            revert InvalidExpiryProof();
        }
        if (!_isValidSignature(root, sig.s, sig.Raddr, sig.nonSigners, sig.refBlock)) {
            revert InvalidApprovalSignature();
        }

        bytes32 slot = _approvalSlot(root);
        uint256 stored;
        assembly {
            stored := tload(slot)
        }
        // First approval wins, so a later call in the same transaction cannot move the
        // reference block that frames already checked their staleness against.
        if (stored == 0) {
            uint256 value = sig.refBlock + 1;
            assembly {
                tstore(slot, value)
            }
        }
    }

    /// @inheritdoc ISchnorrApprovalRegistry
    function approvedRefBlock(bytes32 root) external view override returns (bool approved, uint256 refBlock) {
        bytes32 slot = _approvalSlot(root);
        uint256 stored;
        assembly {
            stored := tload(slot)
        }
        if (stored == 0 || stored - 1 < effectiveBlock) return (false, 0);
        return (true, stored - 1);
    }

    function _approvalSlot(bytes32 root) private pure returns (bytes32) {
        return keccak256(abi.encode(APPROVAL_NAMESPACE, root));
    }

    function _isValidSignature(
        bytes32 message,
        uint256 s,
        address Raddr,
        address[] calldata nonSigners,
        uint256 refBlock
    ) private view returns (bool) {
        if (refBlock >= block.number) revert FutureReferenceBlock();
        // Fail-closed: the cached aggregate/weights only equal their value at refBlock when
        // no operator-set mutation happened after it.
        if (refBlock < effectiveBlock) revert StaleSnapshot();

        // Start from the full aggregate, subtract each non-signer's key and weight.
        uint256 xAgg = aggX;
        uint256 yAgg = aggY;
        uint256 signedWeight = totalWeight;

        address last = address(0);
        uint256 nonSignersLength = nonSigners.length;
        for (uint256 i = 0; i < nonSignersLength; ++i) {
            address ns = nonSigners[i];
            if (ns <= last) revert NonSignersNotSorted();
            last = ns;
            Operator storage op = operators[ns];
            if (!op.registered) revert NotRegistered(ns);
            (xAgg, yAgg) = Secp256k1.sub(xAgg, yAgg, op.x, op.y);
            signedWeight -= op.weight;
        }

        // Stake threshold: signedWeight/total >= num/den.
        if (signedWeight * thresholdDen < totalWeight * thresholdNum) return false;

        // If every operator is a non-signer the aggregate is the identity — reject.
        if (xAgg == 0 && yAgg == 0) return false;

        return SchnorrVerify.verify(xAgg, uint8(yAgg & 1), message, s, Raddr);
    }
}
