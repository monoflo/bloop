import collections
from typing import Any, Dict, Mapping, Optional, Union

import arrow

from ..exceptions import InvalidPosition, InvalidStream, RecordsExpired
from ..session import SessionWrapper
from .buffer import RecordBuffer
from .shard import Shard, unpack_shards


class Coordinator:
    def __init__(self, *, engine, session: SessionWrapper, stream_arn: str):

        self.engine = engine
        self.session = session

        #: The stream that's being coordinated
        self.stream_arn = stream_arn

        #: The oldest shards in each shard tree (no parents)
        self.roots = []

        #: Shards being iterated right now
        self.active = []

        # Single buffer for the lifetime of the Coordinator, but mutates frequently
        # Records in the buffer aren't considered read.  When a Record popped from the buffer is
        # consumed, the Coordinator MUST notify the Shard by updating the sequence_number and iterator_type.
        # The new values should be:
        #   shard.sequence_number = record["meta"]["sequence_number"]
        #   shard.iterator_type = "after_record"

        #: Holds records from advancing all active shard iterators.
        #: Shards aren't advanced again until the buffer drains completely.
        self.buffer = RecordBuffer()

    def __repr__(self):
        # <Coordinator[.../StreamCreation-travis-661.2/stream/2016-10-03T06:17:12.741]>
        return "<{}[{}]>".format(self.__class__.__name__, self.stream_arn)

    def __next__(self) -> Optional[Dict[str, Any]]:
        if not self.buffer:
            self.advance_shards()

        if self.buffer:
            record, shard = self.buffer.pop()

            # Now that the record is "consumed", advance the shard's checkpoint
            shard.sequence_number = record["meta"]["sequence_number"]
            shard.iterator_type = "after_sequence"
            return record

        # No records :(
        return None

    def advance_shards(self) -> None:
        """Try to refill the buffer by collecting records from the active shards.

        Rotates exhausted shards.
        Returns immediately if the buffer isn't empty.
        """
        # Don't poll shards when there are pending records.
        if self.buffer:
            return

        # 0) Collect new records from all active shards.
        record_shard_pairs = []
        for shard in self.active:
            records = next(shard)
            if records:
                record_shard_pairs.extend((record, shard) for record in records)
        self.buffer.push_all(record_shard_pairs)

        self._handle_exhausted()

    def heartbeat(self) -> None:
        """Keep active shards with "latest" and "trim_horizon" iterators alive."""
        for shard in self.active:
            if shard.sequence_number is None:
                records = next(shard)
                # Success!  This shard now has an ``at_sequence`` iterator
                if records:
                    self.buffer.push_all((record, shard) for record in records)
        self._handle_exhausted()

    def _handle_exhausted(self):
        # 1) Clean up exhausted Shards.  Can't modify the active list while iterating it.
        to_remove = [shard for shard in self.active if shard.exhausted]
        for shard in to_remove:
            shard.load_children()
            # Also promotes children to the shard's previous roles
            self.remove_shard(shard)
            for child in shard.children:
                child.jump_to(iterator_type="trim_horizon")

    @property
    def token(self) -> Dict[str, Any]:
        shard_tokens = []
        for root in self.roots:
            for shard in root.walk_tree():
                shard_tokens.append(shard.token)
                shard_tokens[-1].pop("stream_arn")
        return {
            "stream_arn": self.stream_arn,
            "active": [shard.shard_id for shard in self.active],
            "shards": shard_tokens
        }

    def remove_shard(self, shard: Shard) -> None:
        try:
            self.roots.remove(shard)
        except ValueError:
            # Wasn't a root Shard
            pass
        else:
            self.roots.extend(shard.children)

        try:
            self.active.remove(shard)
        except ValueError:
            # Wasn't an active Shard
            pass
        else:
            self.active.extend(shard.children)

        # TODO can this be improved?  Gets expensive for high-volume streams with large buffers
        heap = self.buffer.heap
        # Clear buffered records from the shard.  Each record is (ordering, record, shard)
        to_remove = [x for x in heap if x[2] is shard]
        for x in to_remove:
            heap.remove(x)

    def move_to(self, position: Union[Mapping, arrow.Arrow, str]) -> None:
        if isinstance(position, Mapping):
            move = _move_stream_token
        elif isinstance(position, arrow.Arrow):
            move = _move_stream_time
        elif isinstance(position, str) and position.lower() in ["latest", "trim_horizon"]:
            move = _move_stream_endpoint
        else:
            raise InvalidPosition("Don't know how to move to position {!r}".format(position))
        move(self, position)


def _move_stream_endpoint(coordinator: Coordinator, position: str) -> None:
    """Move to the "trim_horizon" or "latest" of the entire stream."""
    # 0) Everything will be rebuilt from DescribeStream.
    stream_arn = coordinator.stream_arn
    coordinator.roots.clear()
    coordinator.active.clear()
    coordinator.buffer.clear()

    # 1) Build a Dict[str, Shard] of the current Stream from a DescribeStream call
    current_shards = coordinator.session.describe_stream(stream_arn=stream_arn)["Shards"]
    current_shards = unpack_shards(current_shards, stream_arn, coordinator.session)

    # 2) Roots are any shards without parents.
    coordinator.roots.extend(shard for shard in current_shards.values() if not shard.parent)

    # 3.0) Stream trim_horizon is the combined trim_horizon of all roots.
    if position == "trim_horizon":
        for shard in coordinator.roots:
            shard.jump_to(iterator_type="trim_horizon")
        coordinator.active.extend(coordinator.roots)
    # 3.1) Stream latest is the combined latest of all shards without children.
    else:
        for root in coordinator.roots:
            for shard in root.walk_tree():
                if not shard.children:
                    shard.jump_to(iterator_type="latest")
                    coordinator.active.append(shard)


def _move_stream_time(coordinator: Coordinator, time: arrow.Arrow) -> None:
    """Scan through the *entire* Stream for the first record after ``time``.

    This is an extremely expensive, naive algorithm that starts at trim_horizon and simply
    dumps records into the void until the first hit.  General improvements in performance are
    tough; we can use the fact that Shards have a max life of 24hr to pick a pretty-good starting
    point for any Shard trees with 6 generations.  Even then we can't know how close the oldest one
    is to rolling off so we either hit trim_horizon, or iterate an extra Shard more than we need to.

    The corner cases are worse; short trees, recent splits, trees with different branch heights.
    """
    if time > arrow.now():
        _move_stream_endpoint(coordinator, "latest")
        return

    _move_stream_endpoint(coordinator, "trim_horizon")
    shard_trees = collections.deque(coordinator.roots)
    while shard_trees:
        shard = shard_trees.popleft()
        records = shard.seek_to(time)

        # Success!  This section of some Shard tree is at the desired time.
        if records:
            coordinator.buffer.push_all((record, shard) for record in records)

        # Closed shard, keep searching its children.
        elif shard.exhausted:
            coordinator.remove_shard(shard)
            shard_trees.extend(shard.children)


def _move_stream_token(coordinator: Coordinator, token: Mapping[str, Any]) -> None:
    """Move to the Stream position described by the token.

    The following rules are applied when interpolation is required:
    - If a shard does not exist (past the trim_horizon) it is ignored.  If that
      shard had children, its children are also checked against the existing shards.
    - If none of the shards in the token exist, then InvalidStream is raised.
    - If a Shard expects its iterator to point to a SequenceNumber that is now past
      that Shard's trim_horizon, the Shard instead points to trim_horizon.
    """
    stream_arn = coordinator.stream_arn = token["stream_arn"]
    # 0) Everything will be rebuilt from the DescribeStream masked by the token.
    coordinator.roots.clear()
    coordinator.active.clear()
    coordinator.buffer.clear()

    # Injecting the token gives us access to the standard shard management functions
    token_shards = unpack_shards(token["shards"], stream_arn, coordinator.session)
    coordinator.roots = [shard for shard in token_shards.values() if not shard.parent]
    coordinator.active.extend(token_shards[shard_id] for shard_id in token["active"])

    # 1) Build a Dict[str, Shard] of the current Stream from a DescribeStream call
    current_shards = coordinator.session.describe_stream(stream_arn=stream_arn)["Shards"]
    current_shards = unpack_shards(current_shards, stream_arn, coordinator.session)

    # 2) Trying to find an intersection with the actual Stream by walking each root shard's tree.
    #    Prune any Shard with no children that's not part of the actual Stream.
    #    Raise InvalidStream if the entire token is pruned.
    unverified = collections.deque(coordinator.roots)
    while unverified:
        shard = unverified.popleft()
        if shard.shard_id not in current_shards:
            # TODO: log at WARNING for unrecognized shard id
            coordinator.remove_shard(shard)
            unverified.extend(shard.children)

    # 3) Everything was pruned, so the token describes an unknown stream.
    if not coordinator.roots:
        raise InvalidStream("This token has no relation to the actual Stream.")

    # 4) Now that everything's verified, grab new iterators for the coordinator's active Shards.
    for shard in coordinator.active:
        try:
            if shard.iterator_type is None:
                # Descendant of an unknown shard
                shard.iterator_type = "trim_horizon"
            # Move back to the token's specified position
            shard.jump_to(iterator_type=shard.iterator_type, sequence_number=shard.sequence_number)
        except RecordsExpired:
            # This token shard's sequence_number is beyond the trim_horizon.
            # The next closest record is at trim_horizon.
            shard.jump_to(iterator_type="trim_horizon")
            # TODO logger.info "SequenceNumber from token was past trim_horizon, moving to trim_horizon instead"