package org.thehill.hill175.model;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

public final class Entry {
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

    public boolean addMember(String nicknameKey) {
        return members.size() < 2 && members.add(nicknameKey);
    }

    public boolean removeMember(String nicknameKey) {
        return members.remove(nicknameKey);
    }

    public boolean isMember(String nicknameKey) {
        return members.contains(nicknameKey);
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
        return List.copyOf(cameraPoses);
    }

    public boolean addCameraPose(CameraPose pose) {
        if (cameraPoses.size() >= 3) {
            return false;
        }
        cameraPoses.add(pose);
        clearSubmission();
        return true;
    }

    public boolean setCameraPose(int oneBasedIndex, CameraPose pose) {
        int index = oneBasedIndex - 1;
        if (index < 0 || index >= cameraPoses.size()) {
            return false;
        }
        cameraPoses.set(index, pose);
        clearSubmission();
        return true;
    }

    public boolean removeCameraPose(int oneBasedIndex) {
        int index = oneBasedIndex - 1;
        if (index < 0 || index >= cameraPoses.size()) {
            return false;
        }
        cameraPoses.remove(index);
        clearSubmission();
        return true;
    }

    public void clearCameraPoses() {
        cameraPoses.clear();
        clearSubmission();
    }
}
