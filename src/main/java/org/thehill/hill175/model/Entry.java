package org.thehill.hill175.model;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

public final class Entry {
    public static final int MAX_CAMERA_SLOTS = 3;
    public static final int MAX_TITLE_LENGTH = 80;
    public static final int MAX_DESCRIPTION_LENGTH = 750;

    private final UUID id;
    private Category category;
    private final LinkedHashSet<String> members;
    private String worldName;
    private BuildRegion region;
    private int allocationIndex;
    private String title;
    private String description;
    private boolean submitted;
    private Instant submittedAt;
    private final ArrayList<CameraPose> cameraPoses;

    public Entry(UUID id, Category category, Set<String> members, String worldName, BuildRegion region, int allocationIndex) {
        this.id = id;
        this.category = category;
        this.members = new LinkedHashSet<>(members);
        this.worldName = worldName;
        this.region = region;
        this.allocationIndex = allocationIndex;
        this.title = "";
        this.description = "";
        this.cameraPoses = new ArrayList<>();
        for (int slot = 0; slot < MAX_CAMERA_SLOTS; slot++) {
            this.cameraPoses.add(null);
        }
    }

    public UUID id() {
        return id;
    }

    public Category category() {
        return category;
    }

    public void category(Category category) {
        this.category = category;
    }

    public Set<String> members() {
        return Set.copyOf(members);
    }

    public boolean addMember(String participantKey) {
        return members.size() < 2 && members.add(participantKey);
    }

    public boolean removeMember(String participantKey) {
        return members.remove(participantKey);
    }

    public boolean isMember(String participantKey) {
        return members.contains(participantKey);
    }

    public String worldName() {
        return worldName;
    }

    public void worldName(String worldName) {
        this.worldName = worldName;
    }

    public BuildRegion region() {
        return region;
    }

    public void region(BuildRegion region) {
        this.region = region;
    }

    public int allocationIndex() {
        return allocationIndex;
    }

    public void allocationIndex(int allocationIndex) {
        this.allocationIndex = allocationIndex;
    }

    public String title() {
        return title;
    }

    public void title(String title) {
        this.title = title;
        clearSubmission();
    }

    public String description() {
        return description;
    }

    public void description(String description) {
        this.description = description;
        clearSubmission();
    }

    public boolean submitted() {
        return submitted;
    }

    public Instant submittedAt() {
        return submittedAt;
    }

    public void submit(Instant instant) {
        this.submitted = true;
        this.submittedAt = instant;
    }

    public void clearSubmission() {
        this.submitted = false;
        this.submittedAt = null;
    }

    public List<CameraPose> cameraPoses() {
        return cameraPoses.stream()
                .filter(java.util.Objects::nonNull)
                .toList();
    }

    public List<Integer> savedCameraSlots() {
        ArrayList<Integer> slots = new ArrayList<>();
        for (int index = 0; index < cameraPoses.size(); index++) {
            if (cameraPoses.get(index) != null) {
                slots.add(index + 1);
            }
        }
        return List.copyOf(slots);
    }

    public java.util.Optional<CameraPose> cameraPose(int oneBasedIndex) {
        int index = oneBasedIndex - 1;
        if (index < 0 || index >= MAX_CAMERA_SLOTS) {
            return java.util.Optional.empty();
        }
        return java.util.Optional.ofNullable(cameraPoses.get(index));
    }

    public java.util.Optional<Integer> firstEmptyCameraSlot() {
        for (int index = 0; index < cameraPoses.size(); index++) {
            if (cameraPoses.get(index) == null) {
                return java.util.Optional.of(index + 1);
            }
        }
        return java.util.Optional.empty();
    }

    public boolean addCameraPose(CameraPose pose) {
        return firstEmptyCameraSlot()
                .map(slot -> setCameraPose(slot, pose))
                .orElse(false);
    }

    public boolean setCameraPose(int oneBasedIndex, CameraPose pose) {
        int index = oneBasedIndex - 1;
        if (index < 0 || index >= MAX_CAMERA_SLOTS || pose == null) {
            return false;
        }
        cameraPoses.set(index, pose);
        clearSubmission();
        return true;
    }

    public boolean removeCameraPose(int oneBasedIndex) {
        int index = oneBasedIndex - 1;
        if (index < 0 || index >= MAX_CAMERA_SLOTS || cameraPoses.get(index) == null) {
            return false;
        }
        cameraPoses.set(index, null);
        clearSubmission();
        return true;
    }

    public void clearCameraPoses() {
        for (int index = 0; index < cameraPoses.size(); index++) {
            cameraPoses.set(index, null);
        }
        clearSubmission();
    }
}
