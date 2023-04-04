"""
Base Types
"""
# mypy: ignore-errors

from __future__ import annotations

import struct
import time

from typing import (
    cast,
    Any as _Any,
    Optional,
)

from .debugging import ModuleLogger, bacpypes_debugging
from .errors import MissingRequiredParameter
from .pdu import (
    ipv4_address_port_re,
    ipv6_address_port_re,
    host_port_re,
    Address as _Address,
    IPv4Address,
    IPv6Address,
)
from .primitivedata import (
    Atomic,
    BitString,
    Boolean,
    CharacterString,
    Date,
    Double,
    Enumerated,
    Integer,
    Null,
    ObjectType,
    ObjectIdentifier,
    OctetString,
    Real,
    Time,
    Unsigned,
    Unsigned8,
    Unsigned16,
    TagClass,
    TagNumber,
    Tag,
    TagList,
)
from .constructeddata import (
    Any,
    AnyAtomic,
    ArrayOf,
    Choice,
    Sequence,
    SequenceOf,
    ListOf,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class AccessAuthenticationFactorDisable(Enumerated):
    _vendor_range = (64, 65535)
    none = 0
    disabled = 1
    disabledLost = 2
    disabledStolen = 3
    disabledDamaged = 4
    disabledDestroyed = 5


class AccessCredentialDisable(Enumerated):
    _vendor_range = (64, 65535)
    none = 0
    disable = 1
    disableManual = 2
    disableLockout = 3


class AccessCredentialDisableReason(Enumerated):
    disabled = 0
    disabledNeedsProvisioning = 1
    disabledUnassigned = 2
    disabledNotYetActive = 3
    disabledExpired = 4
    disabledLockout = 5
    disabledMaxDays = 6
    disabledMaxUses = 7
    disabledInactivity = 8
    disabledManual = 9


class AccessEvent(Enumerated):
    _vendor_range = (512, 65535)
    none = 0
    granted = 1
    muster = 2
    passbackDetected = 3
    duress = 4
    trace = 5
    lockoutMaxAttempts = 6
    lockoutOther = 7
    lockoutRelinquished = 8
    lockedByHigherPriority = 9
    outOfService = 10
    outOfServiceRelinquished = 11
    accompanimentBy = 12
    authenticationFactorRead = 13
    authorizationDelayed = 14
    verificationRequired = 15
    deniedDenyAll = 128
    deniedUnknownCredential = 129
    deniedAuthenticationUnavailable = 130
    deniedAuthenticationFactorTimeout = 131
    deniedIncorrectAuthenticationFactor = 132
    deniedZoneNoAccessRights = 133
    deniedPointNoAccessRights = 134
    deniedNoAccessRights = 135
    deniedOutOfTimeRange = 136
    deniedThreatLevel = 137
    deniedPassback = 138
    deniedUnexpectedLocationUsage = 139
    deniedMaxAttempts = 140
    deniedLowerOccupancyLimit = 141
    deniedUpperOccupancyLimit = 142
    deniedAuthenticationFactorLost = 143
    deniedAuthenticationFactorStolen = 144
    deniedAuthenticationFactorDamaged = 145
    deniedAuthenticationFactorDestroyed = 146
    deniedAuthenticationFactorDisabled = 147
    deniedAuthenticationFactorError = 148
    deniedCredentialUnassigned = 149
    deniedCredentialNotProvisioned = 150
    deniedCredentialNotYetActive = 151
    deniedCredentialExpired = 152
    deniedCredentialManualDisable = 153
    deniedCredentialLockout = 154
    deniedCredentialMaxDays = 155
    deniedCredentialMaxUses = 156
    deniedCredentialInactivity = 157
    deniedCredentialDisabled = 158
    deniedNoAccompaniment = 159
    deniedIncorrectAccompaniment = 160
    deniedLockout = 161
    deniedVerificationFailed = 162
    deniedVerificationTimeout = 163
    deniedOther = 164


class AccessPassbackMode(Enumerated):
    passbackOff = 0
    hardPassback = 1
    softPassback = 2


class AccessRuleLocationSpecifier(Enumerated):
    specified = 0
    all = 1


class AccessRuleTimeRangeSpecifier(Enumerated):
    specified = 0
    always = 1


class AccessUserType(Enumerated):
    _vendor_range = (64, 65535)
    asset = 0
    group = 1
    person = 2


class AccessZoneOccupancyState(Enumerated):
    _vendor_range = (64, 65535)
    normal = 0
    belowLowerLimit = 1
    atLowerLimit = 2
    atUpperLimit = 3
    aboveUpperLimit = 4
    disabled = 5
    notSupported = 6


class AccumulatorRecordAccumulatorStatus(Enumerated):
    normal = 0
    starting = 1
    recovered = 2
    abnormal = 3
    failed = 4


class Action(Enumerated):
    direct = 0
    reverse = 1


class AuditLevel(Enumerated):
    _vendor_range = (128, 255)
    none = 0
    auditAll = 1
    auditConfig = 2
    default = 3


class AuditOperation(Enumerated):
    _vendor_range = (32, 63)
    read = 0
    write = 1
    create = 2
    delete = 3
    lifeSafety = 4
    acknowledgeAlarm = 5
    deviceDisableComm = 6
    deviceEnableComm = 7
    deviceReset = 8
    deviceBackup = 9
    deviceRestore = 10
    subscription = 11
    notification = 12
    auditingFailure = 13
    networkChanges = 14
    general = 15


class AuthenticationFactorType(Enumerated):
    undefined = 0
    error = 1
    custom = 2
    simpleNumber16 = 3
    simpleNumber32 = 4
    simpleNumber56 = 5
    simpleAlphaNumeric = 6
    abaTrack2 = 7
    wiegand26 = 8
    wiegand37 = 9
    wiegand37facility = 10
    facility16card32 = 11
    facility32card32 = 12
    fascN = 13
    fascNbcd = 14
    fascNlarge = 15
    fascNlargeBcd = 16
    gsa75 = 17
    chuid = 18
    chuidFull = 19
    guid = 20
    cbeffA = 21
    cbeffB = 22
    cbeffC = 23
    userPassword = 24


class AuthenticationStatus(Enumerated):
    notReady = 0
    ready = 1
    disabled = 2
    waitingForAuthenticationFactor = 3
    waitingForAccompaniment = 4
    waitingForVerification = 5
    inProgress = 6


class AuthorizationException(Enumerated):
    _vendor_range = (64, 255)
    passback = 0
    occupancyCheck = 1
    accessRights = 2
    lockout = 3
    deny = 4
    verification = 5
    authorizationDelay = 6


class AuthorizationMode(Enumerated):
    _vendor_range = (64, 65536)
    authorize = 0
    grantActive = 1
    denyAll = 2
    verificationRequired = 3
    authorizationDelayed = 4
    none = 5


class BackupState(Enumerated):
    idle = 0
    preparingForBackup = 1
    preparingForRestore = 2
    performingABackup = 3
    performingARestore = 4
    backupFailure = 5
    restoreFailure = 6


class BinaryLightingPV(Enumerated):
    _vendor_range = (64, 255)
    off = 0
    on = 1
    warn = 2
    warnOff = 3
    warnRelinquish = 4
    stop = 5


class BinaryPV(Enumerated):
    inactive = 0
    active = 1


class ConfirmedTextMessageRequestMessagePriority(Enumerated):
    normal = 0
    urgent = 1


class DeviceCommunicationControlRequestEnableDisable(Enumerated):
    enable = 0
    disable = 1
    disableInitiation = 2


class DeviceStatus(Enumerated):
    _vendor_range = (64, 65535)
    operational = 0
    operationalReadOnly = 1
    downloadRequired = 2
    downloadInProgress = 3
    nonOperational = 4
    backupInProgress = 5


class DoorAlarmState(Enumerated):
    _vendor_range = (256, 65535)
    normal = 0
    alarm = 1
    doorOpenTooLong = 2
    forcedOpen = 3
    tamper = 4
    doorFault = 5
    lockDown = 6
    freeAccess = 7
    egressOpen = 8


class DoorSecuredStatus(Enumerated):
    secured = 0
    unsecured = 1
    unknown = 2


class DoorStatus(Enumerated):
    closed = 0
    opened = 1
    unknown = 2


class DoorValue(Enumerated):
    lock = 0
    unlock = 1
    pulseUnlock = 2
    extendedPulseUnlock = 3


class EngineeringUnits(Enumerated):
    _vendor_range = (256, 65535)  # reserved: 47808...49999
    amperes = 3
    ampereSeconds = 238
    amperesPerMeter = 167
    amperesPerSquareMeter = 168
    ampereSquareHours = 246
    ampereSquareMeters = 169
    bars = 55
    becquerels = 222
    btus = 20
    btusPerHour = 50
    btusPerPound = 117
    btusPerPoundDryAir = 24
    candelas = 179
    candelasPerSquareMeter = 180
    centimeters = 118
    centimetersOfMercury = 60
    centimetersOfWater = 57
    cubicFeet = 79
    cubicFeetPerDay = 248
    cubicFeetPerHour = 191
    cubicFeetPerMinute = 84
    cubicFeetPerSecond = 142
    cubicMeters = 80
    cubicMetersPerDay = 249
    cubicMetersPerHour = 135
    cubicMetersPerMinute = 165
    cubicMetersPerSecond = 85
    currency10 = 114
    currency1 = 105
    currency2 = 106
    currency3 = 107
    currency4 = 108
    currency5 = 109
    currency6 = 110
    currency7 = 111
    currency8 = 112
    currency9 = 113
    cyclesPerHour = 25
    cyclesPerMinute = 26
    days = 70
    decibels = 199
    decibelsA = 232
    decibelsMillivolt = 200
    decibelsVolt = 201
    degreeDaysCelsius = 65
    degreeDaysFahrenheit = 66
    degreesAngular = 90
    degreesCelsius = 62
    degreesCelsiusPerHour = 91
    degreesCelsiusPerMinute = 92
    degreesFahrenheit = 64
    degreesFahrenheitPerHour = 93
    degreesFahrenheitPerMinute = 94
    degreesKelvin = 63
    degreesKelvinPerHour = 181
    degreesKelvinPerMinute = 182
    degreesPhase = 14
    deltaDegreesFahrenheit = 120
    deltaDegreesKelvin = 121
    farads = 170
    feet = 33
    feetPerMinute = 77
    feetPerSecond = 76
    footCandles = 38
    grams = 195
    gramsOfWaterPerKilogramDryAir = 28
    gramsPerCubicCentimeter = 221
    gramsPerCubicMeter = 217
    gramsPerGram = 208
    gramsPerKilogram = 210
    gramsPerLiter = 214
    gramsPerMilliliter = 213
    gramsPerMinute = 155
    gramsPerSecond = 154
    gramsPerSquareMeter = 235
    gray = 225
    hectopascals = 133
    henrys = 171
    hertz = 27
    horsepower = 51
    hours = 71
    hundredthsSeconds = 158
    imperialGallons = 81
    imperialGallonsPerMinute = 86
    inches = 32
    inchesOfMercury = 61
    inchesOfWater = 58
    joules = 16
    jouleSeconds = 183
    joulesPerCubicMeter = 251
    joulesPerDegreeKelvin = 127
    joulesPerHours = 247
    joulesPerKilogramDegreeKelvin = 128
    joulesPerKilogramDryAir = 23
    kilobecquerels = 223
    kiloBtus = 147
    kiloBtusPerHour = 157
    kilograms = 39
    kilogramsPerCubicMeter = 186
    kilogramsPerHour = 44
    kilogramsPerKilogram = 209
    kilogramsPerMinute = 43
    kilogramsPerSecond = 42
    kilohertz = 129
    kilohms = 122
    kilojoules = 17
    kilojoulesPerDegreeKelvin = 151
    kilojoulesPerKilogram = 125
    kilojoulesPerKilogramDryAir = 149
    kilometers = 193
    kilometersPerHour = 75
    kilopascals = 54
    kilovoltAmpereHours = 240
    kilovoltAmpereHoursReactive = 243
    kilovoltAmperes = 9
    kilovoltAmperesReactive = 12
    kilovolts = 6
    kilowattHours = 19
    kilowattHoursPerSquareFoot = 138
    kilowattHoursPerSquareMeter = 137
    kilowattHoursReactive = 204
    kilowatts = 48
    liters = 82
    litersPerHour = 136
    litersPerMinute = 88
    litersPerSecond = 87
    lumens = 36
    luxes = 37
    megabecquerels = 224
    megaBtus = 148
    megahertz = 130
    megajoules = 126
    megajoulesPerDegreeKelvin = 152
    megajoulesPerKilogramDryAir = 150
    megajoulesPerSquareFoot = 140
    megajoulesPerSquareMeter = 139
    megavoltAmpereHours = 241
    megavoltAmpereHoursReactive = 244
    megavoltAmperes = 10
    megavoltAmperesReactive = 13
    megavolts = 7
    megawattHours = 146
    megawattHoursReactive = 205
    megawatts = 49
    megohms = 123
    meters = 31
    metersPerHour = 164
    metersPerMinute = 163
    metersPerSecond = 74
    metersPerSecondPerSecond = 166
    microgramsPerCubicMeter = 219
    microgramsPerLiter = 216
    microgray = 227
    micrometers = 194
    microSiemens = 190
    microsieverts = 230
    microsievertsPerHour = 231
    milesPerHour = 78
    milliamperes = 2
    millibars = 134
    milligrams = 196
    milligramsPerCubicMeter = 218
    milligramsPerGram = 211
    milligramsPerKilogram = 212
    milligramsPerLiter = 215
    milligray = 226
    milliliters = 197
    millilitersPerSecond = 198
    millimeters = 30
    millimetersOfMercury = 59
    millimetersOfWater = 206
    millimetersPerMinute = 162
    millimetersPerSecond = 161
    milliohms = 145
    milliseconds = 159
    millisiemens = 202
    millisieverts = 229
    millivolts = 124
    milliwatts = 132
    minutes = 72
    minutesPerDegreeKelvin = 236
    months = 68
    nanogramsPerCubicMeter = 220
    nephelometricTurbidityUnit = 233
    newton = 153
    newtonMeters = 160
    newtonSeconds = 187
    newtonsPerMeter = 188
    noUnits = 95
    ohmMeterPerSquareMeter = 237
    ohmMeters = 172
    ohms = 4
    partsPerBillion = 97
    partsPerMillion = 96
    pascals = 53
    pascalSeconds = 253
    percent = 98
    percentObscurationPerFoot = 143
    percentObscurationPerMeter = 144
    percentPerSecond = 99
    percentRelativeHumidity = 29
    perHour = 131
    perMille = 207
    perMinute = 100
    perSecond = 101
    pH = 234
    poundsForcePerSquareInch = 56
    poundsMass = 40
    poundsMassPerHour = 46
    poundsMassPerMinute = 45
    poundsMassPerSecond = 119
    powerFactor = 15
    psiPerDegreeFahrenheit = 102
    radians = 103
    radiansPerSecond = 184
    revolutionsPerMinute = 104
    seconds = 73
    siemens = 173
    siemensPerMeter = 174
    sieverts = 228
    squareCentimeters = 116
    squareFeet = 1
    squareInches = 115
    squareMeters = 0
    squareMetersPerNewton = 185
    teslas = 175
    therms = 21
    tonHours = 22
    tons = 41
    tonsPerHour = 156
    tonsRefrigeration = 52
    usGallons = 83
    usGallonsPerHour = 192
    usGallonsPerMinute = 89
    voltAmpereHours = 239
    voltAmpereHoursReactive = 242
    voltAmperes = 8
    voltAmperesReactive = 11
    volts = 5
    voltsPerDegreeKelvin = 176
    voltsPerMeter = 177
    voltsSquareHours = 245
    wattHours = 18
    wattHoursPerCubicMeter = 250
    wattHoursReactive = 203
    watts = 47
    wattsPerMeterPerDegreeKelvin = 189
    wattsPerSquareFoot = 34
    wattsPerSquareMeter = 35
    wattsPerSquareMeterDegreeKelvin = 141
    webers = 178
    weeks = 69
    years = 67


class ErrorClass(Enumerated):
    device = 0
    object = 1
    property = 2
    resources = 3
    security = 4
    services = 5
    vt = 6
    communication = 7


class ErrorCode(Enumerated):
    abortApduTooLong = 123
    abortApplicationExceededReplyTime = 124
    abortBufferOverflow = 51
    abortInsufficientSecurity = 135
    abortInvalidApduInThisState = 52
    abortOther = 56
    abortOutOfResources = 125
    abortPreemptedByHigherPriorityTask = 53
    abortProprietary = 55
    abortSecurityError = 136
    abortSegmentationNotSupported = 54
    abortTsmTimeout = 126
    abortWindowSizeOutOfRange = 127
    accessDenied = 85
    addressingError = 115
    badDestinationAddress = 86
    badDestinationDeviceId = 87
    badSignature = 88
    badSourceAddress = 89
    badTimestamp = 90
    busy = 82
    cannotUseKey = 91
    cannotVerifyMessageId = 92
    characterSetNotSupported = 41
    communicationDisabled = 83
    configurationInProgress = 2
    correctKeyRevision = 93
    covSubscriptionFailed = 43
    datatypeNotSupported = 47
    deleteFdtEntryFailed = 120
    deviceBusy = 3
    destinationDeviceIdRequired = 94
    distributeBroadcastFailed = 121
    duplicateMessage = 95
    duplicateName = 48
    duplicateObjectId = 49
    dynamicCreationNotSupported = 4
    encryptionNotConfigured = 96
    encryptionRequired = 97
    fileAccessDenied = 5
    fileFull = 128
    inconsistentConfiguration = 129
    inconsistentObjectType = 130
    inconsistentParameters = 7
    inconsistentSelectionCriterion = 8
    incorrectKey = 98
    internalError = 131
    invalidArrayIndex = 42
    invalidConfigurationData = 46
    invalidDataType = 9
    invalidEventState = 73
    invalidFileAccessMethod = 10
    invalidFileStartPosition = 11
    invalidKeyData = 99
    invalidParameterDataType = 13
    invalidTag = 57
    invalidTimeStamp = 14
    keyUpdateInProgress = 100
    listElementNotFound = 81
    logBufferFull = 75
    loggedValuePurged = 76
    malformedMessage = 101
    messageTooLong = 113
    missingRequiredParameter = 16
    networkDown = 58
    noAlarmConfigured = 74
    noObjectsOfSpecifiedType = 17
    noPropertySpecified = 77
    noSpaceForObject = 18
    noSpaceToAddListElement = 19
    noSpaceToWriteProperty = 20
    noVtSessionsAvailable = 21
    notConfigured = 132
    notConfiguredForTriggeredLogging = 78
    notCovProperty = 44
    notKeyServer = 102
    notRouterToDnet = 110
    objectDeletionNotPermitted = 23
    objectIdentifierAlreadyExists = 24
    other = 0
    operationalProblem = 25
    optionalFunctionalityNotSupported = 45
    outOfMemory = 133
    parameterOutOfRange = 80
    passwordFailure = 26
    propertyIsNotAList = 22
    propertyIsNotAnArray = 50
    readAccessDenied = 27
    readBdtFailed = 117
    readFdtFailed = 119
    registerForeignDeviceFailed = 118
    rejectBufferOverflow = 59
    rejectInconsistentParameters = 60
    rejectInvalidParameterDataType = 61
    rejectInvalidTag = 62
    rejectMissingRequiredParameter = 63
    rejectParameterOutOfRange = 64
    rejectTooManyArguments = 65
    rejectUndefinedEnumeration = 66
    rejectUnrecognizedService = 67
    rejectProprietary = 68
    rejectOther = 69
    routerBusy = 111
    securityError = 114
    securityNotConfigured = 103
    serviceRequestDenied = 29
    sourceSecurityRequired = 104
    success = 84
    timeout = 30
    tooManyKeys = 105
    unknownAuthenticationType = 106
    unknownDevice = 70
    unknownFileSize = 122
    unknownKey = 107
    unknownKeyRevision = 108
    unknownNetworkMessage = 112
    unknownObject = 31
    unknownProperty = 32
    unknownSubscription = 79
    unknownRoute = 71
    unknownSourceMessage = 109
    unknownVtClass = 34
    unknownVtSession = 35
    unsupportedObjectType = 36
    valueNotInitialized = 72
    valueOutOfRange = 37
    valueTooLong = 134
    vtSessionAlreadyClosed = 38
    vtSessionTerminationFailure = 39
    writeAccessDenied = 40
    writeBdtFailed = 116


class EscalatorFault(Enumerated):
    _vendor_range = (1024, 65535)
    controllerFault = 0
    driveAndMotorFault = 1
    mechanicalComponentFault = 2
    overspeedFault = 3
    powerSupplyFault = 4
    safetyDeviceFault = 5
    controllerSupplyFault = 6
    driveTemperatureExceeded = 7
    combPlateFault = 8


class EscalatorMode(Enumerated):
    _vendor_range = (1024, 65535)
    unknown = 0
    stop = 1
    up = 2
    down = 3
    inspection = 4
    outOfService = 5


class EscalatorOperationDirection(Enumerated):
    _vendor_range = (1024, 65535)
    unknown = 0
    stopped = 1
    upRatedSpeed = 2
    upReducedSpeed = 3
    downRatedSpeed = 4
    downReducedSpeed = 5


class EventState(Enumerated):
    _vendor_range = (64, 65535)
    normal = 0
    fault = 1
    offnormal = 2
    highLimit = 3
    lowLimit = 4
    lifeSafetyAlarm = 5


class EventType(Enumerated):
    _vendor_range = (64, 65535)
    changeOfBitstring = 0
    changeOfState = 1
    changeOfValue = 2
    commandFailure = 3
    floatingLimit = 4
    outOfRange = 5
    changeOfLifeSafety = 8
    extended = 9
    bufferReady = 10
    unsignedRange = 11
    accessEvent = 13
    doubleOutOfRange = 14
    signedOutOfRange = 15
    unsignedOutOfRange = 16
    changeOfCharacterstring = 17
    changeOfStatusFlags = 18
    changeOfReliability = 19


class FaultType(Enumerated):
    none = 0
    faultCharacterstring = 1
    faultExtended = 2
    faultLifeSafety = 3
    faultState = 4
    faultStatusFlags = 5


class FileAccessMethod(Enumerated):
    recordAccess = 0
    streamAccess = 1


class GetEnrollmentSummaryRequestAcknowledgmentFilterType(Enumerated):
    all = 0
    acked = 1
    notAcked = 2


class GetEnrollmentSummaryRequestEventStateFilterType(Enumerated):
    offnormal = 0
    fault = 1
    normal = 2
    all = 3
    active = 4


class IPMode(Enumerated):
    normal = 0
    foreign = 1
    bbmd = 2


class LifeSafetyMode(Enumerated):
    _vendor_range = (256, 65535)
    off = 0
    on = 1
    test = 2
    manned = 3
    unmanned = 4
    armed = 5
    disarmed = 6
    prearmed = 7
    slow = 8
    fast = 9
    disconnected = 10
    enabled = 11
    disabled = 12
    automaticReleaseDisabled = 13
    default = 14


class LifeSafetyOperation(Enumerated):
    _vendor_range = (64, 65535)
    none = 0
    silence = 1
    silenceAudible = 2
    silenceVisual = 3
    reset = 4
    resetAlarm = 5
    resetFault = 6
    unsilence = 7
    unsilenceAudible = 8
    unsilenceVisual = 9


class LifeSafetyState(Enumerated):
    _vendor_range = (256, 65535)
    quiet = 0
    preAlarm = 1
    alarm = 2
    fault = 3
    faultPreAlarm = 4
    faultAlarm = 5
    notReady = 6
    active = 7
    tamper = 8
    testAlarm = 9
    testActive = 10
    testFault = 11
    testFaultAlarm = 12
    holdup = 13
    duress = 14
    tamperAlarm = 15
    abnormal = 16
    emergencyPower = 17
    delayed = 18
    blocked = 19
    localAlarm = 20
    generalAlarm = 21
    supervisory = 22
    testSupervisory = 23


class LiftCarDirection(Enumerated):
    _vendor_range = (1024, 65535)
    unknown = 0
    none = 1
    stopped = 2
    up = 3
    down = 4
    upAndDown = 5


class LiftCarDoorCommand(Enumerated):
    none = 0
    open = 1
    close = 2


class LiftCarDriveStatus(Enumerated):
    _vendor_range = (1024, 65535)
    unknown = 0
    stationary = 1
    braking = 2
    accelerate = 3
    decelerate = 4
    ratedSpeed = 5
    singleFloorJump = 6
    twoFloorJump = 7
    threeFloorJump = 8
    multiFloorJump = 9


class LiftCarMode(Enumerated):
    _vendor_range = (1024, 65535)
    unknown = 0
    normal = 1
    vip = 2
    homing = 3
    parking = 4
    attendantControl = 5
    firefighterControl = 6
    emergencyPower = 7
    inspection = 8
    cabinetRecall = 9
    earthquakeOperation = 10
    fireOperation = 11
    outOfService = 12
    occupantEvacuation = 13


class LiftFault(Enumerated):
    _vendor_range = (1024, 65535)
    controllerFault = 0
    driveAndMotorFault = 1
    governorAndSafetyGearFault = 2
    liftShaftDeviceFault = 3
    powerSupplyFault = 4
    safetyInterlockFault = 5
    doorClosingFault = 6
    doorOpeningFault = 7
    carStoppedOutsideLandingZone = 8
    callButtonStuck = 9
    startFailure = 10
    controllerSupplyFault = 11
    selfTestFailure = 12
    runtimeLimitExceeded = 13
    positionLost = 14
    driveTemperatureExceeded = 15
    loadMeasurementFault = 16


class LiftGroupMode(Enumerated):
    unknown = 0
    normal = 1
    downPeak = 2
    twoWay = 3
    fourWay = 4
    emergencyPower = 5
    upPeak = 6


class LightingInProgress(Enumerated):
    idle = 0
    fadeActive = 1
    rampActive = 2
    notControlled = 3
    other = 4


class LightingOperation(Enumerated):
    _vendor_range = (256, 65535)
    none = 0
    fadeTo = 1
    rampTo = 2
    stepUp = 3
    stepDown = 4
    stepOn = 5
    stepOff = 6
    warn = 7
    warnOff = 8
    warnRelinquish = 9
    stop = 10


class LightingTransition(Enumerated):
    _vendor_range = (64, 255)
    none = 0
    fade = 1
    ramp = 2


class LockStatus(Enumerated):
    locked = 0
    unlocked = 1
    fault = 2
    unknown = 3


class LoggingType(Enumerated):
    _vendor_range = (64, 255)
    polled = 0
    cov = 1
    triggered = 2


class Maintenance(Enumerated):
    _vendor_range = (256, 65535)
    none = 0
    periodicTest = 1
    needServiceOperational = 2
    needServiceInoperative = 3


class NetworkNumberQuality(Enumerated):
    unknown = 0
    learned = 1
    learnedConfigured = 2
    configured = 3


class NetworkPortCommand(Enumerated):
    _vendor_range = (128, 255)
    idle = 0
    discardChanges = 1
    renewFdDRegistration = 2
    restartSlaveDiscovery = 3
    renewDHCP = 4
    restartAutonegotiation = 5
    disconnect = 6
    restartPort = 7


class NetworkType(Enumerated):
    _vendor_range = (64, 255)
    ethernet = 0
    arcnet = 1
    mstp = 2
    ptp = 3
    lontalk = 4
    ipv4 = 5
    zigbee = 6
    virtual = 7
    ipv6 = 9
    serial = 10


class NodeType(Enumerated):
    unknown = 0
    system = 1
    network = 2
    device = 3
    organizational = 4
    area = 5
    equipment = 6
    point = 7
    collection = 8
    property = 9
    functional = 10
    other = 11


class NotifyType(Enumerated):
    alarm = 0
    event = 1
    ackNotification = 2


class Polarity(Enumerated):
    normal = 0
    reverse = 1


class ProgramError(Enumerated):
    _vendor_range = (64, 65535)
    normal = 0
    loadFailed = 1
    internal = 2
    program = 3
    other = 4


class ProgramRequest(Enumerated):
    ready = 0
    load = 1
    run = 2
    halt = 3
    restart = 4
    unload = 5


class ProgramState(Enumerated):
    idle = 0
    loading = 1
    running = 2
    waiting = 3
    halted = 4
    unloading = 5


class PropertyIdentifier(Enumerated):
    _vendor_range = (512, 4194303)
    absenteeLimit = 244
    acceptedModes = 175
    accessAlarmEvents = 245
    accessDoors = 246
    accessEvent = 247
    accessEventAuthenticationFactor = 248
    accessEventCredential = 249
    accessEventTag = 322
    accessEventTime = 250
    accessTransactionEvents = 251
    accompaniment = 252
    accompanimentTime = 253
    ackedTransitions = 0
    ackRequired = 1
    action = 2
    actionText = 3
    activationTime = 254
    activeAuthenticationPolicy = 255
    activeCovMultipleSubscriptions = 481
    activeCovSubscriptions = 152
    activeText = 4
    activeVtSessions = 5
    actualShedLevel = 212
    adjustValue = 176
    alarmValue = 6
    alarmValues = 7
    alignIntervals = 193
    all = 8
    allowGroupDelayInhibit = 365
    allWritesSuccessful = 9
    apduLength = 388
    apduSegmentTimeout = 10
    apduTimeout = 11
    applicationSoftwareVersion = 12
    archive = 13
    assignedAccessRights = 256
    assignedLandingCalls = 447
    attemptedSamples = 124
    auditableOperations = 501
    auditLevel = 498
    auditNotificationRecipient = 499
    auditPriorityFilter = 500
    auditSourceReporter = 497
    authenticationFactors = 257
    authenticationPolicyList = 258
    authenticationPolicyNames = 259
    authenticationStatus = 260
    authorizationExemptions = 364
    authorizationMode = 261
    autoSlaveDiscovery = 169
    averageValue = 125
    backupAndRestoreState = 338
    backupFailureTimeout = 153
    backupPreparationTime = 339
    bacnetIPGlobalAddress = 407
    bacnetIPMode = 408
    bacnetIPMulticastAddress = 409
    bacnetIPNATTraversal = 410
    bacnetIPUDPPort = 412
    bacnetIPv6Mode = 435
    bacnetIPv6MulticastAddress = 440
    bacnetIPv6UDPPort = 438
    baseDeviceSecurityPolicy = 327
    bbmdAcceptFDRegistrations = 413
    bbmdBroadcastDistributionTable = 414
    bbmdForeignDeviceTable = 415
    belongsTo = 262
    bias = 14
    bitMask = 342
    bitText = 343
    blinkWarnEnable = 373
    bufferSize = 126
    carAssignedDirection = 448
    carDoorCommand = 449
    carDoorStatus = 450
    carDoorText = 451
    carDoorZone = 452
    carDriveStatus = 453
    carLoad = 454
    carLoadUnits = 455
    carMode = 456
    carMovingDirection = 457
    carPosition = 458
    changeOfStateCount = 15
    changeOfStateTime = 16
    changesPending = 416
    channelNumber = 366
    clientCovIncrement = 127
    command = 417
    commandTimeArray = 430
    configurationFiles = 154
    controlGroups = 367
    controlledVariableReference = 19
    controlledVariableUnits = 20
    controlledVariableValue = 21
    count = 177
    countBeforeChange = 178
    countChangeTime = 179
    covIncrement = 22
    covPeriod = 180
    covResubscriptionInterval = 128
    covuPeriod = 349
    covuRecipients = 350
    credentialDisable = 263
    credentials = 265
    credentialsInZone = 266
    credentialStatus = 264
    currentCommandPriority = 431
    databaseRevision = 155
    dateList = 23
    daylightSavingsStatus = 24
    daysRemaining = 267
    deadband = 25
    defaultFadeTime = 374
    defaultPresentValue = 492
    defaultRampRate = 375
    defaultStepIncrement = 376
    defaultSubordinateRelationship = 490
    defaultTimeout = 393
    deleteOnForward = 502
    deployedProfileLocation = 484
    derivativeConstant = 26
    derivativeConstantUnits = 27
    description = 28
    descriptionOfHalt = 29
    deviceAddressBinding = 30
    deviceType = 31
    deviceUUID = 507
    directReading = 156
    distributionKeyRevision = 328
    doNotHide = 329
    doorAlarmState = 226
    doorExtendedPulseTime = 227
    doorMembers = 228
    doorOpenTooLongTime = 229
    doorPulseTime = 230
    doorStatus = 231
    doorUnlockDelayTime = 232
    dutyWindow = 213
    effectivePeriod = 32
    egressActive = 386
    egressTime = 377
    elapsedActiveTime = 33
    elevatorGroup = 459
    enable = 133
    energyMeter = 460
    energyMeterRef = 461
    entryPoints = 268
    errorLimit = 34
    escalatorMode = 462
    eventAlgorithmInhibit = 354
    eventAlgorithmInhibitRef = 355
    eventDetectionEnable = 353
    eventEnable = 35
    eventMessageTexts = 351
    eventMessageTextsConfig = 352
    eventParameters = 83
    eventState = 36
    eventTimeStamps = 130
    eventType = 37
    exceptionSchedule = 38
    executionDelay = 368
    exitPoints = 269
    expectedShedLevel = 214
    expirationTime = 270
    extendedTimeEnable = 271
    failedAttemptEvents = 272
    failedAttempts = 273
    failedAttemptsTime = 274
    faultHighLimit = 388
    faultLowLimit = 389
    faultParameters = 358
    faultSignals = 463
    faultType = 359
    faultValues = 39
    fdBBMDAddress = 418
    fdSubscriptionLifetime = 419
    feedbackValue = 40
    fileAccessMethod = 41
    fileSize = 42
    fileType = 43
    firmwareRevision = 44
    floorNumber = 506
    floorText = 464
    fullDutyBaseline = 215
    globalIdentifier = 323
    groupID = 465
    groupMemberNames = 346
    groupMembers = 345
    groupMode = 467
    higherDeck = 468
    highLimit = 45
    inactiveText = 46
    initialTimeout = 394
    inProcess = 47
    inProgress = 378
    inputReference = 181
    installationID = 469
    instanceOf = 48
    instantaneousPower = 379
    integralConstant = 49
    integralConstantUnits = 50
    interfaceValue = 387
    intervalOffset = 195
    ipAddress = 400
    ipDefaultGateway = 401
    ipDHCPEnable = 402
    ipDHCPLeaseTime = 403
    ipDHCPLeaseTimeRemaining = 404
    ipDHCPServer = 405
    ipDNSServer = 406
    ipSubnetMask = 411
    ipv6Address = 436
    ipv6AutoAddressingEnabled = 442
    ipv6DefaultGateway = 439
    ipv6DHCPLeaseTime = 443
    ipv6DHCPLeaseTimeRemaining = 444
    ipv6DHCPServer = 445
    ipv6DNSServer = 441
    ipv6PrefixLength = 437
    ipv6ZoneIndex = 446
    issueConfirmedNotifications = 51
    isUTC = 344
    keySets = 330
    landingCallControl = 471
    landingCalls = 470
    landingDoorStatus = 472
    lastAccessEvent = 275
    lastAccessPoint = 276
    lastCommandTime = 432
    lastCredentialAdded = 277
    lastCredentialAddedTime = 278
    lastCredentialRemoved = 279
    lastCredentialRemovedTime = 280
    lastKeyServer = 331
    lastNotifyRecord = 173
    lastPriority = 369
    lastRestartReason = 196
    lastRestoreTime = 157
    lastStateChange = 395
    lastUseTime = 281
    lifeSafetyAlarmValues = 166
    lightingCommand = 380
    lightingCommandDefaultPriority = 381
    limitEnable = 52
    limitMonitoringInterval = 182
    linkSpeed = 420
    linkSpeedAutonegotiate = 422
    linkSpeeds = 421
    listOfGroupMembers = 53
    listOfObjectPropertyReferences = 54
    listOfSessionKeys = 55
    localDate = 56
    localForwardingOnly = 360
    localTime = 57
    location = 58
    lockout = 282
    lockoutRelinquishTime = 283
    lockStatus = 233
    logBuffer = 131
    logDeviceObjectProperty = 132
    loggingObject = 183
    loggingRecord = 184
    loggingType = 197
    logInterval = 134
    lowDiffLimit = 390
    lowerDeck = 473
    lowLimit = 59
    macAddress = 423
    machineRoomID = 474
    maintenanceRequired = 158
    makingCarCall = 475
    manipulatedVariableReference = 60
    manualSlaveAddressBinding = 170
    maskedAlarmValues = 234
    masterExemption = 284
    maxActualValue = 382
    maxApduLengthAccepted = 62
    maxFailedAttempts = 285
    maximumOutput = 61
    maximumSendDelay = 503
    maximumValue = 135
    maximumValueTimestamp = 149
    maxInfoFrames = 63
    maxMaster = 64
    maxPresValue = 65
    maxSegmentsAccepted = 167
    memberOf = 159
    members = 286
    memberStatusFlags = 347
    minActualValue = 383
    minimumOffTime = 66
    minimumOnTime = 67
    minimumOutput = 68
    minimumValue = 136
    minimumValueTimestamp = 150
    minPresValue = 69
    mode = 160
    modelName = 70
    modificationDate = 71
    monitoredObjects = 504
    musterPoint = 287
    negativeAccessRules = 288
    networkAccessSecurityPolicies = 332
    networkInterfaceName = 424
    networkNumber = 425
    networkNumberQuality = 426
    networkType = 427
    nextStoppingFloor = 476
    nodeSubtype = 207
    nodeType = 208
    notificationClass = 17
    notificationThreshold = 137
    notifyType = 72
    numberOfApduRetries = 73
    numberOfAuthenticationPolicies = 289
    numberOfStates = 74
    objectIdentifier = 75
    objectList = 76
    objectName = 77
    objectPropertyReference = 78
    objectType = 79
    occupancyCount = 290
    occupancyCountAdjust = 291
    occupancyCountEnable = 292
    occupancyExemption = 293
    occupancyLowerLimit = 294
    occupancyLowerLimitEnforced = 295
    occupancyState = 296
    occupancyUpperLimit = 297
    occupancyUpperLimitEnforced = 298
    operationDirection = 477
    operationExpected = 161
    optional = 80
    outOfService = 81
    outputUnits = 82
    packetReorderTime = 333
    passbackExemption = 299
    passbackMode = 300
    passbackTimeout = 301
    passengerAlarm = 478
    polarity = 84
    portFilter = 363
    positiveAccessRules = 302
    power = 384
    powerMode = 479
    prescale = 185
    presentStage = 493
    presentValue = 85
    priority = 86
    priorityArray = 87
    priorityForWriting = 88
    processIdentifier = 89
    processIdentifierFilter = 361
    profileLocation = 91
    profileName = 168
    programChange = 90
    programLocation = 91
    programState = 92
    propertyList = 371
    proportionalConstant = 93
    proportionalConstantUnits = 94
    protocolLevel = 482
    protocolObjectTypesSupported = 96
    protocolRevision = 139
    protocolServicesSupported = 97
    protocolVersion = 98
    pulseRate = 186
    readOnly = 99
    reasonForDisable = 303
    reasonForHalt = 100
    recipientList = 102
    recordCount = 141
    recordsSinceNotification = 140
    referencePort = 483
    registeredCarCall = 480
    reliability = 103
    reliabilityEvaluationInhibit = 357
    relinquishDefault = 104
    represents = 491
    requestedShedLevel = 218
    requestedUpdateInterval = 348
    required = 105
    resolution = 106
    restartNotificationRecipients = 202
    restoreCompletionTime = 340
    restorePreparationTime = 341
    routingTable = 428
    scale = 187
    scaleFactor = 188
    scheduleDefault = 174
    securedStatus = 235
    securityPDUTimeout = 334
    securityTimeWindow = 335
    segmentationSupported = 107
    sendNow = 505
    serialNumber = 372
    setpoint = 108
    setpointReference = 109
    setting = 162
    shedDuration = 219
    shedLevelDescriptions = 220
    shedLevels = 221
    silenced = 163
    slaveAddressBinding = 171
    slaveProxyEnable = 172
    stageNames = 495
    stages = 494
    startTime = 142
    stateChangeValues = 396
    stateDescription = 222
    stateText = 110
    statusFlags = 111
    stopTime = 143
    stopWhenFull = 144
    strikeCount = 391
    structuredObjectList = 209
    subordinateAnnotations = 210
    subordinateList = 211
    subordinateNodeTypes = 487
    subordinateRelationships = 489
    subordinateTags = 488
    subscribedRecipients = 362
    supportedFormatClasses = 305
    supportedFormats = 304
    supportedSecurityAlgorithms = 336
    systemStatus = 112
    tags = 486
    targetReferences = 496
    threatAuthority = 306
    threatLevel = 307
    timeDelay = 113
    timeDelayNormal = 356
    timeOfActiveTimeReset = 114
    timeOfDeviceRestart = 203
    timeOfStateCountReset = 115
    timeOfStrikeCountReset = 392
    timerRunning = 397
    timerState = 398
    timeSynchronizationInterval = 204
    timeSynchronizationRecipients = 116
    totalRecordCount = 145
    traceFlag = 308
    trackingValue = 164
    transactionNotificationClass = 309
    transition = 385
    trigger = 205
    units = 117
    updateInterval = 118
    updateKeySetTimeout = 337
    updateTime = 189
    userExternalIdentifier = 310
    userInformationReference = 311
    userName = 317
    userType = 318
    usesRemaining = 319
    utcOffset = 119
    utcTimeSynchronizationRecipients = 206
    validSamples = 146
    valueBeforeChange = 190
    valueChangeTime = 192
    valueSet = 191
    valueSource = 433
    valueSourceArray = 434
    varianceValue = 151
    vendorIdentifier = 120
    vendorName = 121
    verificationTime = 326
    virtualMACAddressTable = 429
    vtClassesSupported = 122
    weeklySchedule = 123
    windowInterval = 147
    windowSamples = 148
    writeStatus = 370
    zoneFrom = 320
    zoneMembers = 165
    zoneTo = 321


class ProtocolLevel(Enumerated):
    physical = 0
    protocol = 1
    bacnetApplication = 2
    nonBacnetApplication = 3


class ReinitializeDeviceRequestReinitializedStateOfDevice(Enumerated):
    coldstart = 0
    warmstart = 1
    startBackup = 2
    endBackup = 3
    startRestore = 4
    endRestore = 5
    abortRestore = 6
    activateChanges = 7


class Relationship(Enumerated):
    _vendor_range = (1024, 65535)
    unknown = 0
    default = 1
    contains = 2
    containedBy = 3
    uses = 4
    usedBy = 5
    commands = 6
    commandedBy = 7
    adjusts = 8
    adjustedBy = 9
    ingress = 10
    egress = 11
    suppliesAir = 12
    receivesAir = 13
    suppliesHotAir = 14
    receivesHotAir = 15
    suppliesCoolAir = 16
    receivesCoolAir = 17
    suppliesPower = 18
    receivesPower = 19
    suppliesGas = 20
    receivesGas = 21
    suppliesWater = 22
    receivesWater = 23
    suppliesHotWater = 24
    receivesHotWater = 25
    suppliesCoolWater = 26
    receivesCoolWater = 27
    suppliesSteam = 28
    receivesSteam = 29


class Reliability(Enumerated):
    _vendor_range = (64, 65535)
    noFaultDetected = 0
    noSensor = 1
    overRange = 2
    underRange = 3
    openLoop = 4
    shortedLoop = 5
    noOutput = 6
    unreliableOther = 7
    processError = 8
    multiStateFault = 9
    configurationError = 10
    communicationFailure = 12
    memberFault = 13
    monitoredObjectFault = 14
    tripped = 15
    lampFailure = 16
    activationFailure = 17
    renewDHCPFailure = 18
    renewFDRegistrationFailure = 19
    restartAutoNegotiationFailure = 20
    restartFailure = 21
    proprietaryCommandFailure = 22
    faultsListed = 23
    referencedObjectFault = 24


class RestartReason(Enumerated):
    _vendor_range = (64, 255)
    unknown = 0
    coldstart = 1
    warmstart = 2
    detectedPowerLost = 3
    detectedPoweredOff = 4
    hardwareWatchdog = 5
    softwareWatchdog = 6
    suspended = 7


class RouterEntryStatus(Enumerated):
    available = 0
    busy = 1
    disconnected = 2


class SecurityLevel(Enumerated):
    incapable = 0
    plain = 1
    signed = 2
    encrypted = 3
    signedEndToEnd = 4
    encryptedEndToEnd = 4


class SecurityPolicy(Enumerated):
    plainNonTrusted = 0
    plainTrusted = 1
    signedTrusted = 2
    encryptedTrusted = 3


class Segmentation(Enumerated):
    segmentedBoth = 0
    segmentedTransmit = 1
    segmentedReceive = 2
    noSegmentation = 3


class ShedState(Enumerated):
    shedInactive = 0
    shedRequestPending = 1
    shedCompliant = 2
    shedNonCompliant = 3


class SilencedState(Enumerated):
    _vendor_range = (64, 65535)
    unsilenced = 0
    audibleSilenced = 1
    visibleSilenced = 2
    allSilenced = 3


class TimerState(Enumerated):
    idle = 0
    running = 1
    expired = 2


class TimerTransition(Enumerated):
    none = 0
    idleToRunning = 1
    runningToIdle = 2
    runningToRunning = 3
    runningToExpired = 4
    forcedToExpired = 5
    expiredToIdle = 6
    expiredToRunning = 7


class UnconfirmedTextMessageRequestMessagePriority(Enumerated):
    normal = 0
    urgent = 1


class VTClass(Enumerated):
    _vendor_range = (64, 65535)
    defaultTerminal = 0
    ansiX364 = 1
    decVt52 = 2
    decVt100 = 3
    decVt220 = 4
    hp70094 = 5
    ibm3130 = 6


class WriteStatus(Enumerated):
    idle = 0
    inProgress = 1
    successful = 2
    failed = 3


#
#
#


class AuditOperationFlags(BitString):
    _vendor_range = (32, 63)
    read = 0
    write = 1
    create = 2
    delete = 3
    lifeSafety = 4
    acknowledgeAlarm = 5
    deviceDisableComm = 6
    deviceEnableComm = 7
    deviceReset = 8
    deviceBackup = 9
    deviceRestore = 10
    subscription = 11
    notification = 12
    auditingFailure = 13
    networkChanges = 14
    general = 15


class DaysOfWeek(BitString):
    monday = 0
    tuesday = 1
    wednesday = 2
    thursday = 3
    friday = 4
    saturday = 5
    sunday = 6


class EventTransitionBits(BitString):
    toOffnormal = 0
    toFault = 1
    toNormal = 2


class LimitEnable(BitString):
    lowLimitEnable = 0
    highLimitEnable = 1


class LogStatus(BitString):
    logDisabled = 0
    bufferPurged = 1
    logInterrupted = 2


class ObjectTypesSupported(BitString):
    analogInput = 0
    analogOutput = 1
    analogValue = 2
    binaryInput = 3
    binaryOutput = 4
    binaryValue = 5
    calendar = 6
    command = 7
    device = 8
    eventEnrollment = 9
    file = 10
    group = 11
    loop = 12
    multiStateInput = 13
    multiStateOutput = 14
    notificationClass = 15
    program = 16
    schedule = 17
    averaging = 18
    multiStateValue = 19
    trendLog = 20
    lifeSafetyPoint = 21
    lifeSafetyZone = 22
    accumulator = 23
    pulseConverter = 24
    eventLog = 25
    globalGroup = 26
    trendLogMultiple = 27
    loadControl = 28
    structuredView = 29
    accessDoor = 30
    accessCredential = 32
    accessPoint = 33
    accessRights = 34
    accessUser = 35
    accessZone = 36
    credentialDataInput = 37
    networkPort = 56
    networkSecurity = 38
    bitstringValue = 39
    characterstringValue = 40
    datePatternValue = 41
    dateValue = 42
    datetimePatternValue = 43
    datetimeValue = 44
    integerValue = 45
    largeAnalogValue = 46
    octetstringValue = 47
    positiveIntegerValue = 48
    timePatternValue = 49
    timeValue = 50
    notificationForwarder = 51
    alertEnrollment = 52
    channel = 53
    lightingOutput = 54


class PriorityFilter(BitString):
    manualLifeSafety = 0
    automaticLifeSafety = 1
    priority3 = 2
    priority4 = 3
    criticalEquipmentControls = 4
    minimumOnOff = 5
    priority7 = 6
    manualOperator = 7
    priority9 = 8
    priority10 = 9
    priority11 = 10
    priority12 = 11
    priority13 = 12
    priority14 = 13
    priority15 = 14
    priority16 = 15


class ResultFlags(BitString):
    firstItem = 0
    lastItem = 1
    moreItems = 2


class ServicesSupported(BitString):
    acknowledgeAlarm = 0
    confirmedCOVNotification = 1
    confirmedEventNotification = 2
    getAlarmSummary = 3
    getEnrollmentSummary = 4
    subscribeCOV = 5
    atomicReadFile = 6
    atomicWriteFile = 7
    addListElement = 8
    removeListElement = 9
    createObject = 10
    deleteObject = 11
    readProperty = 12
    # readPropertyConditional = 13  # removed in version 1 revision 12
    readPropertyMultiple = 14
    writeProperty = 15
    writePropertyMultiple = 16
    deviceCommunicationControl = 17
    confirmedPrivateTransfer = 18
    confirmedTextMessage = 19
    reinitializeDevice = 20
    vtOpen = 21
    vtClose = 22
    vtData = 23
    # authenticate = 24  # removed in version 1 revision 11
    # requestKey = 25  # removed in version 1 revision 11
    iAm = 26
    iHave = 27
    unconfirmedCOVNotification = 28
    unconfirmedEventNotification = 29
    unconfirmedPrivateTransfer = 30
    unconfirmedTextMessage = 31
    timeSynchronization = 32
    whoHas = 33
    whoIs = 34
    readRange = 35
    utcTimeSynchronization = 36
    lifeSafetyOperation = 37
    subscribeCOVProperty = 38
    getEventInformation = 39
    writeGroup = 40


class StatusFlags(BitString):
    inAlarm = 0
    fault = 1
    overridden = 2
    outOfService = 3


#
#
#


class AccessThreatLevel(Unsigned):
    _low_limit = 0
    _high_limit = 100


#
#
#


class MACAddress(OctetString):
    @classmethod
    def cast(cls, arg):
        if isinstance(arg, (str, int, bytes, bytearray)):
            return _Address(arg).addrAddr
        else:
            raise TypeError(type(arg))


class IPOctetString(OctetString):
    @classmethod
    def cast(cls, arg):
        if isinstance(arg, str):
            if ipv4_address_port_re.match(arg):
                return IPv4Address(arg).addrAddr
            elif ipv6_address_port_re.match(arg):
                return IPv6Address(arg).addrAddr
            else:
                raise ValueError(arg)
        elif isinstance(arg, (bytes, bytearray)):
            if (len(arg) != 6) and (len(arg) != 18):
                raise ValueError("4 or 16 octets expected")
            return arg
        else:
            raise TypeError(type(arg))

    def __repr__(self) -> str:
        if len(self) == 6:
            return str(IPv4Address(self))
        elif len(self) == 18:
            return str(IPv6Address(self))
        else:
            return OctetString.__repr__(self)


class IPv4OctetString(OctetString):
    @classmethod
    def cast(cls, arg):
        if isinstance(arg, str):
            return IPv4Address(arg).addrAddr[:4]
        elif isinstance(arg, (bytes, bytearray)):
            if len(arg) != 4:
                raise ValueError("4 octets expected")
            return arg
        else:
            raise TypeError(type(arg))

    def __repr__(self):
        return str(IPv4Address(self + b"\xBA\xC0"))


class IPv6OctetString(OctetString):
    @classmethod
    def cast(cls, arg):
        if isinstance(arg, str):
            return IPv6Address(arg).addrAddr[:16]
        elif isinstance(arg, (bytes, bytearray)):
            if len(arg) != 16:
                raise ValueError("16 octets expected")
            return arg
        else:
            raise TypeError(type(arg))

    def __repr__(self):
        return str(IPv6Address(self + b"\xBA\xC0"))


#
#
#


class PropertyReference(Sequence):
    _order = ("propertyIdentifier", "propertyArrayIndex")
    propertyIdentifier = PropertyIdentifier(_context=0)
    propertyArrayIndex = Unsigned(_context=1, _optional=True)


class PropertyValue(Sequence):
    _order = ("propertyIdentifier", "propertyArrayIndex", "value", "priority")
    propertyIdentifier = PropertyIdentifier(_context=0)
    propertyArrayIndex = Unsigned(_context=1, _optional=True)
    value = Any(_context=2)
    priority = Unsigned(_context=3, _optional=True)


class ObjectPropertyReference(Sequence):
    _order = ("objectIdentifier", "propertyIdentifier", "propertyArrayIndex")
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)


class ObjectPropertyValue(Sequence):
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "value",
        "priority",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    value = Any(_context=3)
    priority = Unsigned(_context=4, _optional=True)


class DeviceObjectPropertyReference(Sequence):
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "deviceIdentifier",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    deviceIdentifier = ObjectIdentifier(_context=3, _optional=True)


class DeviceObjectPropertyValue(Sequence):
    _order = (
        "deviceIdentifier",
        "objectIdentifier",
        "propertyIdentifier",
        "arrayIndex",
        "value",
    )
    deviceIdentifier = ObjectIdentifier(_context=0)
    objectIdentifier = ObjectIdentifier(_context=1)
    propertyIdentifier = PropertyIdentifier(_context=2)
    arrayIndex = Unsigned(_context=3, _optional=True)
    value = Any(_context=4)


class DeviceObjectReference(Sequence):
    _order = ("deviceIdentifier", "objectIdentifier")
    deviceIdentifier = ObjectIdentifier(_context=0, _optional=True)
    objectIdentifier = ObjectIdentifier(_context=1)


class DateTime(Sequence):
    _order = ("date", "time")
    date = Date
    time = Time

    @classmethod
    def now(cls: type, when: Optional[float] = None) -> DateTime:
        """
        Return the current date and time.
        """
        if when is None:
            when = time.time()

        # return an instance
        return cast(DateTime, cls(date=Date.now(when), time=Time.now(when)))


class TimeValue(Sequence):
    _order = ("time", "value")
    time = Time()
    value = AnyAtomic()


class DeviceAddress(Sequence):
    _order = ("networkNumber", "macAddress")
    networkNumber = Unsigned()
    macAddress = OctetString()


_sequence_number = 0


class TimeStamp(Choice):
    time = Time(_context=0)
    sequenceNumber = Unsigned(_context=1)
    dateTime = DateTime(_context=2)

    @classmethod
    def as_time(cls: type, when: Optional[float] = None) -> TimeStamp:
        return cls(time=Time.now(when))

    @classmethod
    def as_sequenceNumber(cls: type, when: Optional[int] = None) -> TimeStamp:
        global _sequence_number
        if when is None:
            _sequence_number += 1
            now = _sequence_number % 65536
        return cls(sequenceNumber=now)

    @classmethod
    def as_dateTime(cls: type, when: Optional[float] = None) -> TimeStamp:
        return cls(dateTime=DateTime.now(when))


class Recipient(Choice):
    device = ObjectIdentifier(_context=0)
    address = DeviceAddress(_context=1)


class ListOfRecipient(ListOf(Recipient)):
    pass


class ErrorType(Sequence):
    _order = ("errorClass", "errorCode")
    errorClass = ErrorClass()
    errorCode = ErrorCode()


@bacpypes_debugging
class HostAddress(Choice):
    none = Null()
    ipAddress = OctetString()
    name = CharacterString()

    def __init__(
        self,
        arg: Optional[str] = None,
        **kwargs,
    ) -> None:
        if _debug:
            HostAddress._debug("HostAddress.__init__ %r %r", arg, kwargs)

        if arg is None:
            pass
        elif isinstance(arg, (IPv4Address, IPv6Address)):
            kwargs["ipAddress"] = arg.addrAddr[:-2]
        elif isinstance(arg, str):
            if ipv4_address_port_re.match(arg):
                kwargs["ipAddress"] = IPv4Address(arg).addrAddr[:-2]
            elif ipv6_address_port_re.match(arg):
                kwargs["ipAddress"] = IPv6Address(arg).addrAddr[:-2]
            else:
                kwargs["name"] = arg
        elif isinstance(arg, (bytes, bytearray)):
            kwargs["ipAddress"] = arg
        elif isinstance(arg, dict):
            ip_address = arg.get("ipAddress", None) or arg.get("ip-address", None)
            if ip_address:
                if isinstance(ip_address, (bytes, bytearray)):
                    kwargs["ipAddress"] = ip_address
                elif ipv4_address_port_re.match(ip_address):
                    kwargs["ipAddress"] = IPv4Address(ip_address).addrAddr[:-2]
                elif ipv6_address_port_re.match(ip_address):
                    kwargs["ipAddress"] = IPv6Address(ip_address).addrAddr[:-2]
                else:
                    raise ValueError(f"ipAddress: {ip_address}")
            if "name" in arg:
                kwargs["name"] = arg["name"]
        else:
            raise TypeError(type(arg))

        super().__init__(**kwargs)

    @classmethod
    def cast(cls, arg):
        if _debug:
            HostAddress._debug("HostAddress.cast %r", arg)

        if isinstance(arg, (bytes, bytearray, str, dict, IPv4Address, IPv6Address)):
            return arg
        else:
            raise TypeError(type(arg))


@bacpypes_debugging
class HostNPort(Sequence):
    _order = ("host", "port")
    host = HostAddress(_context=0)
    port = Unsigned16(_context=1)

    _address: _Address

    def __init__(
        self,
        arg: Optional[str] = None,
        *,
        host: Optional[HostAddress] = None,
        port: Optional[int] = None,
    ) -> None:
        if _debug:
            HostAddress._debug("HostNPort.__init__ %r host=%r port=%r", arg, host, port)

        addr = None

        # avoid the extra cast call
        host_address_class = HostNPort.host.__class__

        if arg is None:
            pass
        elif isinstance(arg, (IPv4Address, IPv6Address)):
            host = host_address_class(ipAddress=arg.addrAddr[:-2])
            port = arg.addrPort
        elif isinstance(arg, str):
            if host_port_re.match(arg) and not ipv4_address_port_re.match(arg):
                host, port = host_port_re.match(arg).groups()  # no walrus :-(
            else:
                addr = _Address(arg)
                if isinstance(addr, (IPv4Address, IPv6Address)):
                    host = host_address_class(ipAddress=addr.addrAddr[:-2])
                    port = addr.addrPort
                else:
                    raise ValueError(f"unsupported: {arg!r}")
        elif isinstance(arg, dict):
            host = arg.get("host", None)
            port = arg.get("port", None)
        elif isinstance(arg, HostNPort):
            host = arg.host
            port = arg.port
        else:
            raise TypeError(type(arg))

        # port is required
        if port is None:
            port = 47808
        if _debug:
            HostNPort._debug("    - host, port, addr: %r, %r, %r", host, port, addr)

        super().__init__(host=host, port=port)

        # save the captured address
        self._address = addr

    @classmethod
    def cast(cls, arg):
        if _debug:
            HostNPort._debug("cast %r", arg)

        if isinstance(arg, (str, dict, IPv4Address, IPv6Address, HostNPort)):
            return arg
        else:
            raise TypeError(type(arg))

    @property
    def address(self) -> _Address:
        """
        Interpret the contents returning an Address that has all the
        tuples necessary for sockets.
        """
        if _debug:
            HostNPort._debug("address")

        if self._address is None:
            if self.host.none is not None:
                return None

            if self.host.name:
                raise NotImplementedError("HostNPort by name")

            addrAddr = self.host.ipAddress
            addrPort = struct.pack(">H", self.port)

            if len(addrAddr) == 4:
                self._address = IPv4Address(addrAddr + addrPort)

            elif len(addrAddr) == 16:
                self._address = IPv6Address(addrAddr + addrPort)
            else:
                raise ValueError(f"host ipAddress {addrAddr!r}")

        return self._address


class AccessRule(Sequence):
    _order = (
        "timeRangeSpecifier",
        "timeRange",
        "locationSpecifier",
        "location",
        "enable",
    )
    timeRangeSpecifier = AccessRuleTimeRangeSpecifier(_context=0)
    timeRange = DeviceObjectPropertyReference(_context=1, _optional=True)
    locationSpecifier = AccessRuleLocationSpecifier(_context=2)
    location = DeviceObjectReference(_context=3, _optional=True)
    enable = Boolean(_context=4)


class ArrayOfAccessRule(ArrayOf(AccessRule)):
    pass


class AccumulatorRecord(Sequence):
    _order = ("timestamp", "presentValue", "accumulatedValue", "accumulatorStatus")
    timestamp = DateTime(_context=0)
    presentValue = Unsigned(_context=1)
    accumulatedValue = Unsigned(_context=2)
    accumulatorStatus = AccumulatorRecordAccumulatorStatus(_context=3)


class ActionCommand(Sequence):
    _order = (
        "deviceIdentifier",
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "propertyValue",
        "priority",
        "postDelay",
        "quitOnFailure",
        "writeSuccessFul",
    )
    deviceIdentifier = ObjectIdentifier(_context=0, _optional=True)
    objectIdentifier = ObjectIdentifier(_context=1)
    propertyIdentifier = PropertyIdentifier(_context=2)
    propertyArrayIndex = Unsigned(_context=3, _optional=True)
    propertyValue = Any(_context=4)
    priority = Unsigned(_context=5, _optional=True)
    postDelay = Unsigned(_context=6, _optional=True)
    quitOnFailure = Boolean(_context=7)
    writeSuccessFul = Boolean(_context=8)


class SequenceOfActionCommand(SequenceOf(ActionCommand)):
    pass


class ActionList(Sequence):
    _order = ("action",)
    action = SequenceOf(ActionCommand, _context=0)


class ArrayOfActionList(ArrayOf(ActionList)):
    pass


class Address(Sequence):
    _order = ("networkNumber", "macAddress")
    networkNumber = Unsigned16()
    macAddress = OctetString()


class AddressBinding(Sequence):
    _order = ("deviceObjectIdentifier", "deviceAddress")
    deviceObjectIdentifier = ObjectIdentifier()
    deviceAddress = DeviceAddress()


class ListOfAddressBinding(ListOf(AddressBinding)):
    pass


class AssignedAccessRights(Sequence):
    _order = ("assignedAccessRights", "enable")
    assignedAccessRights = DeviceObjectReference(_context=0)
    enable = Boolean(_context=1)


class ArrayOfAssignedAccessRights(ArrayOf(AssignedAccessRights)):
    pass


class AssignedLandingCallsLandingCalls(Sequence):
    _order = ("floorNumber", "direction")
    floorNumber = Unsigned8(_context=0)
    direction = LiftCarDirection(_context=1)


class SequenceOfAssignedLandingCallsLandingCalls(
    SequenceOf(AssignedLandingCallsLandingCalls)
):
    pass


class AssignedLandingCalls(Sequence):
    _order = ("landingCalls",)
    landingCalls = SequenceOf(AssignedLandingCallsLandingCalls, _context=0)


class ArrayOfAssignedLandingCalls(ArrayOf(AssignedLandingCalls)):
    pass


class AtomicReadFileACKAccessMethodRecordAccess(Sequence):
    _order = ("fileStartRecord", "returnedRecordCount", "fileRecordData")
    fileStartRecord = Integer()
    returnedRecordCount = Unsigned()
    fileRecordData = SequenceOf(OctetString)


class AtomicReadFileACKAccessMethodStreamAccess(Sequence):
    _order = ("fileStartPosition", "fileData")
    fileStartPosition = Integer()
    fileData = OctetString()


class AtomicReadFileRequestAccessMethodChoiceRecordAccess(Sequence):
    _order = ("fileStartRecord", "requestedRecordCount")
    fileStartRecord = Integer()
    requestedRecordCount = Unsigned()


class AtomicReadFileRequestAccessMethodChoiceStreamAccess(Sequence):
    _order = ("fileStartPosition", "requestedOctetCount")
    fileStartPosition = Integer()
    requestedOctetCount = Unsigned()


class AtomicWriteFileRequestAccessMethodChoiceRecordAccess(Sequence):
    _order = ("fileStartRecord", "recordCount", "fileRecordData")
    fileStartRecord = Integer()
    recordCount = Unsigned()
    fileRecordData = SequenceOf(OctetString)


class AtomicWriteFileRequestAccessMethodChoiceStreamAccess(Sequence):
    _order = ("fileStartPosition", "fileData")
    fileStartPosition = Integer()
    fileData = OctetString()


class AuditLogQueryParametersBySource(Sequence):
    _order = (
        "sourceDeviceIdentifier",
        "sourceDeviceAddress",
        "sourceObjectIdentifier",
        "operations",
        "successfulActionsOnly",
    )
    sourceDeviceIdentifier = ObjectIdentifier(_context=0)
    sourceDeviceAddress = Address(_context=1, _optional=True)
    sourceObjectIdentifier = ObjectIdentifier(_context=2, _optional=True)
    operations = AuditOperationFlags(_context=3, _optional=True)
    successfulActionsOnly = Boolean(_context=4)


class AuditLogQueryParametersByTarget(Sequence):
    _order = (
        "targetDeviceIdentifier",
        "targetDeviceAddress",
        "targetObjectIdentifier",
        "targetPropertyIdentifier",
        "targetArrayIndex",
        "targetPriority",
        "operations",
        "successfulActionsOnly",
    )
    targetDeviceIdentifier = ObjectIdentifier(_context=0)
    targetDeviceAddress = Address(_context=1, _optional=True)
    targetObjectIdentifier = ObjectIdentifier(_context=2, _optional=True)
    targetPropertyIdentifier = PropertyIdentifier(_context=3, _optional=True)
    targetArrayIndex = Unsigned(_context=4, _optional=True)
    targetPriority = Unsigned(_context=5, _optional=True)
    operations = AuditOperationFlags(_context=6, _optional=True)
    successfulActionsOnly = Boolean(_context=7)


class AuditNotification(Sequence):
    _order = (
        "sourceTimestamp",
        "targetTimestamp",
        "sourceDevice",
        "sourceObject",
        "operation",
        "sourceComment",
        "targetComment",
        "invokeID",
        "sourceUserID",
        "sourceUserRole",
        "targetDevice",
        "targetObject",
        "targetProperty",
        "targetPriority",
        "targetValue",
        "currentValue",
        "result",
    )
    sourceTimestamp = TimeStamp(_context=0, _optional=True)
    targetTimestamp = TimeStamp(_context=1, _optional=True)
    sourceDevice = Recipient(_context=2)
    sourceObject = ObjectIdentifier(_context=3, _optional=True)
    operation = AuditOperation(_context=4)
    sourceComment = CharacterString(_context=5, _optional=True)
    targetComment = CharacterString(_context=6, _optional=True)
    invokeID = Unsigned8(_context=7, _optional=True)
    sourceUserID = Unsigned16(_context=8, _optional=True)
    sourceUserRole = Unsigned8(_context=9, _optional=True)
    targetDevice = Recipient(_context=10)
    targetObject = ObjectIdentifier(_context=11, _optional=True)
    targetProperty = PropertyReference(_context=12, _optional=True)
    targetPriority = Unsigned(_context=13, _optional=True)
    targetValue = Any(_context=14, _optional=True)
    currentValue = Any(_context=15, _optional=True)
    result = ErrorType(_context=16, _optional=True)


class AuditLogRecordLogDatum(Choice):
    logStatus = LogStatus(_context=0)
    auditNotification = AuditNotification(_context=1)
    timeChange = Real()


class AuditLogRecord(Sequence):
    _order = ("timestamp", "logDatum")
    timestamp = DateTime(_context=0)
    logDatum = AuditLogRecordLogDatum(_context=1)


class ListOfAuditLogRecord(ListOf(AuditLogRecord)):
    pass


class AuditLogRecordResult(Sequence):
    _order = ("sequenceNumber", "logRecord")
    sequenceNumber = Unsigned(_context=0)
    logRecord = AuditLogRecord(_context=1)


class AuthenticationFactor(Sequence):
    _order = ("formatType", "formatClass", "value")
    formatType = AuthenticationFactorType(_context=0)
    formatClass = Unsigned(_context=1)
    value = OctetString(_context=2)


class AuthenticationFactorFormat(Sequence):
    _order = ("formatType", "vendorId", "vendorFormat")
    formatType = AuthenticationFactorType(_context=0)
    vendorId = Unsigned(_context=1, _optional=True)
    vendorFormat = Unsigned(_context=2, _optional=True)


class ArrayOfAuthenticationFactorFormat(ArrayOf(AuthenticationFactorFormat)):
    pass


class AuthenticationPolicyPolicy(Sequence):
    _order = ("credentialDataInput", "index")
    credentialDataInput = DeviceObjectReference(_context=0)
    index = Unsigned(_context=1)


class SequenceOfAuthenticationPolicyPolicy(SequenceOf(AuthenticationPolicyPolicy)):
    pass


class AuthenticationPolicy(Sequence):
    _order = ("policy", "orderEnforced", "timeout")
    policy = SequenceOf(AuthenticationPolicyPolicy, _context=0)
    orderEnforced = Boolean(_context=1)
    timeout = Unsigned(_context=2)


class ArrayOfAuthenticationPolicy(ArrayOf(AuthenticationPolicy)):
    pass


class BDTEntry(Sequence):
    _order = ("bbmdAddress", "broadcastMask")
    bbmdAddress = HostNPort(_context=0)
    broadcastMask = IPv4OctetString(_context=1, _optional=True)

    _address: _Address

    def __init__(
        self,
        arg: Optional[str] = None,
        *,
        bbmdAddress: Optional[HostNPort] = None,
        broadcastMask: Optional[IPv4OctetString] = None,
    ) -> None:
        addr = None

        if arg is None:
            pass
        elif isinstance(arg, str):
            if bbmdAddress is not None:
                raise ValueError("__init__ conflict: bbmdAddress")

            # avoid the extra cast call
            bbmdAddress = BDTEntry.bbmdAddress.__class__(arg)

            # if a host name was provided, nothing more to do until the
            # name is resolved
            if bbmdAddress.host.name:
                pass
            else:
                addr = bbmdAddress.address
                if isinstance(addr, IPv4Address) and (broadcastMask is None):
                    broadcastMask = addr.netmask.packed
                    if broadcastMask != b"\xFF\xFF\xFF\xFF":
                        addr = None
        else:
            raise TypeError(type(arg))

        super().__init__(bbmdAddress=bbmdAddress, broadcastMask=broadcastMask)

        # cache it
        self._address = addr

    @classmethod
    def cast(cls, arg):
        if isinstance(arg, (str, dict)):
            return arg
        else:
            raise TypeError(type(arg))

    @property
    def address(self) -> _Address:
        """
        Interpret the contents returning an Address that has all the
        tuples necessary for sockets.
        """
        if not self._address:
            self._address = addr = self.bbmdAddress.address
            if isinstance(addr, IPv4Address) and (
                self.broadcastMask != b"\xFF\xFF\xFF\xFF"
            ):
                addr_str = ".".join(str(i) for i in addr.addrAddr[:-2])
                mask_str = ".".join(str(i) for i in self.broadcastMask)
                self._address = _Address(f"{addr_str}/{mask_str}", addr.addrPort)

        return self._address


class ListOfBDTEntry(ListOf(BDTEntry)):
    pass


class RecipientProcess(Sequence):
    _order = ("recipient", "processIdentifier")
    recipient = Recipient(_context=0)
    processIdentifier = Unsigned(_context=1)


class COVMultipleSubscriptionListOfCOVReference(Sequence):
    _order = ("monitoredProperty", "covIncrement", "timestamped")
    monitoredProperty = PropertyReference(_context=0)
    covIncrement = Real(_context=1, _optional=True)
    timestamped = Boolean(_context=2)


class SequenceOfCOVMultipleSubscriptionListOfCOVReference(
    SequenceOf(COVMultipleSubscriptionListOfCOVReference)
):
    pass


class COVMultipleSubscriptionList(Sequence):
    _order = ("monitoredObjectIdentifier", "listOfCOVReferences")
    monitoredObjectIdentifier = ObjectIdentifier(_context=0)
    listOfCOVReferences = SequenceOf(
        COVMultipleSubscriptionListOfCOVReference, _context=1
    )


class SequenceOfCOVMultipleSubscriptionList(SequenceOf(COVMultipleSubscriptionList)):
    pass


class COVMultipleSubscription(Sequence):
    _order = (
        "recipient",
        "issueConfirmedNotifications",
        "timeRemaining",
        "maxNotificationDelay",
        "listOfCOVSubscriptionSpecifications",
    )
    recipient = RecipientProcess(_context=0)
    issueConfirmedNotifications = Boolean(_context=1)
    timeRemaining = Unsigned(_context=2)
    maxNotificationDelay = Unsigned(_context=3)
    listOfCOVSubscriptionSpecifications = SequenceOf(
        COVMultipleSubscriptionList, _context=4
    )


class ListOfCOVMultipleSubscription(ListOf(COVMultipleSubscription)):
    pass


class COVNotificationParameters(Sequence):
    _order = (
        "subscriberProcessIdentifier",
        "initiatingDeviceIdentifier",
        "monitoredObjectIdentifier",
        "timeRemaining",
        "listOfValues",
    )
    subscriberProcessIdentifier = Unsigned(_context=0)
    initiatingDeviceIdentifier = ObjectIdentifier(_context=1)
    monitoredObjectIdentifier = ObjectIdentifier(_context=2)
    timeRemaining = Unsigned(_context=3)
    listOfValues = SequenceOf(PropertyValue, _context=4)


class COVSubscription(Sequence):
    _order = (
        "recipient",
        "monitoredPropertyReference",
        "issueConfirmedNotifications",
        "timeRemaining",
        "covIncrement",
    )
    recipient = RecipientProcess(_context=0)
    monitoredPropertyReference = ObjectPropertyReference(_context=1)
    issueConfirmedNotifications = Boolean(_context=2)
    timeRemaining = Unsigned(_context=3)
    covIncrement = Real(_context=4, _optional=True)


class ListOfCOVSubscription(ListOf(COVSubscription)):
    pass


class CredentialAuthenticationFactor(Sequence):
    _order = ("disable", "authenticationFactor")
    disable = AccessAuthenticationFactorDisable(_context=0)
    authenticationFactor = AuthenticationFactor(_context=1)


class ArrayOfCredentialAuthenticationFactor(ArrayOf(CredentialAuthenticationFactor)):
    pass


class DailySchedule(Sequence):
    _order = ("daySchedule",)
    daySchedule = SequenceOf(TimeValue, _context=0)


class ArrayOfDailySchedule(ArrayOf(DailySchedule)):
    pass


class DateRange(Sequence):
    _order = ("startDate", "endDate")
    startDate = Date()
    endDate = Date()


class Destination(Sequence):
    _order = (
        "validDays",
        "fromTime",
        "toTime",
        "recipient",
        "processIdentifier",
        "issueConfirmedNotifications",
        "transitions",
    )
    validDays = DaysOfWeek()
    fromTime = Time()
    toTime = Time()
    recipient = Recipient()
    processIdentifier = Unsigned()
    issueConfirmedNotifications = Boolean()
    transitions = EventTransitionBits()


class ListOfDestination(ListOf(Destination)):
    pass


class PropertyStates(Choice):
    booleanValue = Boolean(_context=0)
    binaryValue = BinaryPV(_context=1)
    eventType = EventType(_context=2)
    polarity = Polarity(_context=3)
    programChange = ProgramRequest(_context=4)
    programState = ProgramState(_context=5)
    reasonForHalt = ProgramError(_context=6)
    reliability = Reliability(_context=7)
    state = EventState(_context=8)
    systemStatus = DeviceStatus(_context=9)
    units = EngineeringUnits(_context=10)
    unsignedValue = Unsigned(_context=11)
    lifeSafetyMode = LifeSafetyMode(_context=12)
    lifeSafetyState = LifeSafetyState(_context=13)
    restartReason = RestartReason(_context=14)
    doorAlarmState = DoorAlarmState(_context=15)
    action = Action(_context=16)
    doorSecuredStatus = DoorSecuredStatus(_context=17)
    doorStatus = DoorStatus(_context=18)
    doorValue = DoorValue(_context=19)
    fileAccessMethod = FileAccessMethod(_context=20)
    lockStatus = LockStatus(_context=21)
    lifeSafetyOperation = LifeSafetyOperation(_context=22)
    maintenance = Maintenance(_context=23)
    nodeType = NodeType(_context=24)
    notifyType = NotifyType(_context=25)
    securityLevel = SecurityLevel(_context=26)
    shedState = ShedState(_context=27)
    silencedState = SilencedState(_context=28)
    accessEvent = AccessEvent(_context=30)
    zoneOccupancyState = AccessZoneOccupancyState(_context=31)
    accessCredentialDisableReason = AccessCredentialDisableReason(_context=32)
    accessCredentialDisable = AccessCredentialDisable(_context=33)
    authenticationStatus = AuthenticationStatus(_context=34)
    backupState = BackupState(_context=36)
    writeStatus = WriteStatus(_context=370)
    lightingInProgress = LightingInProgress(_context=38)
    lightingOperation = LightingOperation(_context=39)
    lightingTransition = LightingTransition(_context=40)


class SequenceOfPropertyStates(SequenceOf(PropertyStates)):
    pass


class NotificationParametersChangeOfBitstring(Sequence):
    _order = ("referencedBitstring", "statusFlags")
    referencedBitstring = BitString(_context=0)
    statusFlags = StatusFlags(_context=1)


class NotificationParametersChangeOfLifeSafety(Sequence):
    _order = ("newState", "newMode", "statusFlags", "operationExpected")
    newState = LifeSafetyState(_context=0)
    newMode = LifeSafetyMode(_context=1)
    statusFlags = StatusFlags(_context=2)
    operationExpected = LifeSafetyOperation(_context=3)


class NotificationParametersChangeOfState(Sequence):
    _order = ("newState", "statusFlags")
    newState = PropertyStates(_context=0)
    statusFlags = StatusFlags(_context=1)


class NotificationParametersChangeOfValueNewValue(Choice):
    changedBits = BitString(_context=0)
    changedValue = Real(_context=1)


class NotificationParametersChangeOfValue(Sequence):
    _order = ("newValue", "statusFlags")
    newValue = NotificationParametersChangeOfValueNewValue(_context=0)
    statusFlags = StatusFlags(_context=1)


class NotificationParametersCommandFailure(Sequence):
    _order = ("commandValue", "statusFlags", "feedbackValue")
    commandValue = Any(_context=0)
    statusFlags = StatusFlags(_context=1)
    feedbackValue = Any(_context=2)


class NotificationParametersFloatingLimit(Sequence):
    _order = ("referenceValue", "statusFlags", "setpointValue", "errorLimit")
    referenceValue = Real(_context=0)
    statusFlags = StatusFlags(_context=1)
    setpointValue = Real(_context=2)
    errorLimit = Real(_context=3)


class NotificationParametersOutOfRange(Sequence):
    _order = ("exceedingValue", "statusFlags", "deadband", "exceededLimit")
    exceedingValue = Real(_context=0)
    statusFlags = StatusFlags(_context=1)
    deadband = Real(_context=2)
    exceededLimit = Real(_context=3)


class NotificationParametersComplexEventType(Sequence):
    _order = ("complexEventType",)
    complexEventType = PropertyValue(_context=0)


class NotificationParametersDoubleOutOfRangeType(Sequence):
    _order = ("exceedingValue", "statusFlags", "deadband", "exceededLimit")
    exceedingValue = Double(_context=0)
    statusFlags = StatusFlags(_context=1)
    deadband = Double(_context=2)
    exceededLimit = Double(_context=3)


class NotificationParametersSignedOutOfRangeType(Sequence):
    _order = ("exceedingValue", "statusFlags", "deadband", "exceededLimit")
    exceedingValue = Integer(_context=0)
    statusFlags = StatusFlags(_context=1)
    deadband = Unsigned(_context=2)
    exceededLimit = Integer(_context=3)


class NotificationParametersUnsignedOutOfRangeType(Sequence):
    _order = ("exceedingValue", "statusFlags", "deadband", "exceededLimit")
    exceedingValue = Unsigned(_context=0)
    statusFlags = StatusFlags(_context=1)
    deadband = Unsigned(_context=2)
    exceededLimit = Unsigned(_context=3)


class NotificationParametersChangeOfCharacterStringType(Sequence):
    _order = ("changedValue", "statusFlags", "alarmValue")
    changedValue = CharacterString(_context=0)
    statusFlags = StatusFlags(_context=1)
    alarmValue = CharacterString(_context=2)


class NotificationParametersChangeOfStatusFlagsType(Sequence):
    _order = ("presentValue", "referencedFlags")
    presentValue = CharacterString(_context=0)
    referencedFlags = StatusFlags(_context=1)


class NotificationParametersChangeOfReliabilityType(Sequence):
    _order = ("reliability", "statusFlags", "propertyValues")
    reliability = Reliability(_context=0)
    statusFlags = StatusFlags(_context=1)
    propertyValues = SequenceOf(PropertyValue, _context=2)


class NotificationParametersAccessEventType(Sequence):
    _order = (
        "accessEvent",
        "statusFlags",
        "accessEventTag",
        "accessEventTime",
        "accessCredential",
        "authenicationFactor",
    )
    accessEvent = AccessEvent(_context=0)
    statusFlags = StatusFlags(_context=1)
    accessEventTag = Unsigned(_context=2)
    accessEventTime = TimeStamp(_context=3)
    accessCredential = DeviceObjectReference(_context=4)
    authenicationFactor = AuthenticationFactorType(_context=5, _optional=True)


class NotificationParametersExtendedParametersType(Choice):
    null = Null()
    real = Real()
    integer = Unsigned()
    boolean = Boolean()
    double = Double()
    octet = OctetString()
    bitstring = BitString()
    enum = Enumerated()
    propertyValue = DeviceObjectPropertyValue()


class NotificationParametersExtended(Sequence):
    _order = ("vendorId", "extendedEventType", "parameters")
    vendorId = Unsigned(_context=0)
    extendedEventType = Unsigned(_context=1)
    parameters = NotificationParametersExtendedParametersType(_context=2)


class NotificationParametersBufferReady(Sequence):
    _order = ("bufferProperty", "previousNotification", "currentNotification")
    bufferProperty = DeviceObjectPropertyReference(_context=0)
    previousNotification = Unsigned(_context=1)
    currentNotification = Unsigned(_context=2)


class NotificationParametersUnsignedRange(Sequence):
    _order = ("exceedingValue", "statusFlags", "exceedingLimit")
    exceedingValue = Unsigned(_context=0)
    statusFlags = StatusFlags(_context=1)
    exceedingLimit = Unsigned(_context=2)


class NotificationParameters(Choice):
    changeOfBitstring = NotificationParametersChangeOfBitstring(_context=0)
    changeOfState = NotificationParametersChangeOfState(_context=1)
    changeOfValue = NotificationParametersChangeOfValue(_context=2)
    commandFailure = NotificationParametersCommandFailure(_context=3)
    floatingLimit = NotificationParametersFloatingLimit(_context=4)
    outOfRange = NotificationParametersOutOfRange(_context=5)
    complexEventType = NotificationParametersComplexEventType(_context=6)
    changeOfLifeSafety = NotificationParametersChangeOfLifeSafety(_context=8)
    extended = NotificationParametersExtended(_context=9)
    bufferReady = NotificationParametersBufferReady(_context=10)
    unsignedRange = NotificationParametersUnsignedRange(_context=11)
    accessEvent = NotificationParametersAccessEventType(_context=13)
    doubleOutOfRange = NotificationParametersDoubleOutOfRangeType(_context=14)
    signedOutOfRange = NotificationParametersSignedOutOfRangeType(_context=15)
    unsignedOutOfRange = NotificationParametersUnsignedOutOfRangeType(_context=16)
    changeOfCharacterString = NotificationParametersChangeOfCharacterStringType(
        _context=17
    )
    changeOfStatusFlags = NotificationParametersChangeOfStatusFlagsType(_context=18)
    changeOfReliability = NotificationParametersChangeOfReliabilityType(_context=19)


class EventNotificationParameters(Sequence):
    _order = (
        "processIdentifier",
        "initiatingDeviceIdentifier",
        "eventObjectIdentifier",
        "timeStamp",
        "notificationClass",
        "priority",
        "eventType",
        "messageText",
        "notifyType",
        "ackRequired",
        "fromState",
        "toState",
        "eventValues",
    )
    processIdentifier = Unsigned(_context=0)
    initiatingDeviceIdentifier = ObjectIdentifier(_context=1)
    eventObjectIdentifier = ObjectIdentifier(_context=2)
    timeStamp = TimeStamp(_context=3)
    notificationClass = Unsigned(_context=4)
    priority = Unsigned(_context=5)
    eventType = EventType(_context=6)
    messageText = CharacterString(_context=7, _optional=True)
    notifyType = NotifyType(_context=8)
    ackRequired = Boolean(_context=9, _optional=True)
    fromState = EventState(_context=10, _optional=True)
    toState = EventState(_context=11)
    eventValues = NotificationParameters(_context=12, _optional=True)


class EventLogRecordLogDatum(Choice):
    logStatus = LogStatus(_context=0)
    notification = EventNotificationParameters(_context=1)
    timeChange = Real(_context=2)


class EventLogRecord(Sequence):
    _order = ("timestamp", "logDatum")
    timestamp = DateTime(_context=0)
    logDatum = EventLogRecordLogDatum(_context=1)


class ListOfEventLogRecord(ListOf(EventLogRecord)):
    pass


class EventNotificationSubscription(Sequence):
    _order = (
        "recipient",
        "processIdentifier",
        "issueConfirmedNotifications",
        "timeRemaining",
    )
    recipient = Recipient(_context=0)
    processIdentifier = Unsigned(_context=1)
    issueConfirmedNotifications = Boolean(_context=2)
    timeRemaining = Unsigned(_context=3)


class ListOfEventNotificationSubscription(ListOf(EventNotificationSubscription)):
    pass


class EventParameterAccessEventAccessEvent(Sequence):
    _order = ("listOfAccessEvents", "accessEventTimeReference")
    listOfAccessEvents = SequenceOf(AccessEvent, _context=0)
    accessEventTimeReference = DeviceObjectPropertyReference(_context=1)


class SequenceOfEventParameterAccessEventAccessEvent(
    SequenceOf(EventParameterAccessEventAccessEvent)
):
    pass


class EventParameterAccessEvent(Sequence):
    _order = ("accessEvent",)
    accessEvent = SequenceOf(EventParameterAccessEventAccessEvent, _context=0)


class EventParameterBufferReady(Sequence):
    _order = ("notificationThreshold", "previousNotificationCount")
    notificationThreshold = Unsigned(_context=0)
    previousNotificationCount = Unsigned(_context=1)


class EventParameterChangeOfBitstring(Sequence):
    _order = ("timeDelay", "bitmask", "listOfBitstringValues")
    timeDelay = Unsigned(_context=0)
    bitmask = BitString(_context=1)
    listOfBitstringValues = SequenceOf(BitString, _context=2)


class EventParameterChangeOfCharacterString(Sequence):
    _order = ("timeDelay", "listOfAlarmValues")
    timeDelay = Unsigned(_context=0)
    listOfAlarmValues = SequenceOf(CharacterString, _context=1)


class EventParameterChangeOfLifeSafety(Sequence):
    _order = (
        "timeDelay",
        "listOfLifeSafetyAlarmValues",
        "listOfAlarmValues",
        "modePropertyReference",
    )
    timeDelay = Unsigned(_context=0)
    listOfLifeSafetyAlarmValues = SequenceOf(LifeSafetyState, _context=1)
    listOfAlarmValues = SequenceOf(LifeSafetyState, _context=2)
    modePropertyReference = DeviceObjectPropertyReference(_context=3)


class EventParameterChangeOfState(Sequence):
    _order = ("timeDelay", "listOfValues")
    timeDelay = Unsigned(_context=0)
    listOfValues = SequenceOf(PropertyStates, _context=1)


class EventParameterChangeOfStatusFlags(Sequence):
    _order = ("timeDelay", "selectedFlags")
    timeDelay = Unsigned(_context=0)
    selectedFlags = StatusFlags(_context=1)


class EventParameterChangeOfValueCOVCriteria(Choice):
    bitmask = BitString(_context=0)
    referencedPropertyIncrement = Real(_context=1)


class EventParameterChangeOfValue(Sequence):
    _order = ("timeDelay", "covCriteria")
    timeDelay = Unsigned(_context=0)
    covCriteria = EventParameterChangeOfValueCOVCriteria(_context=1)


class EventParameterCommandFailure(Sequence):
    _order = ("timeDelay", "feedbackPropertyReference")
    timeDelay = Unsigned(_context=0)
    feedbackPropertyReference = DeviceObjectPropertyReference(_context=1)


class EventParameterDoubleOutOfRange(Sequence):
    _order = ("timeDelay", "lowLimit", "highLimit", "deadband")
    timeDelay = Unsigned(_context=0)
    lowLimit = Double(_context=1)
    highLimit = Double(_context=2)
    deadband = Double(_context=3)


class EventParameterExtendedParameters(Choice):
    null = Null(_context=0)
    real = Real(_context=1)
    integer = Unsigned(_context=2)
    boolean = Boolean(_context=3)
    double = Double(_context=4)
    octet = OctetString(_context=5)
    bitstring = BitString(_context=6)
    enum = Enumerated(_context=7)
    reference = DeviceObjectPropertyReference(_context=8)


class SequenceOfEventParameterExtendedParameters(
    SequenceOf(EventParameterExtendedParameters)
):
    pass


class EventParameterExtended(Sequence):
    _order = ("vendorId", "extendedEventType", "parameters")
    vendorId = Unsigned(_context=0)
    extendedEventType = Unsigned(_context=1)
    parameters = SequenceOf(EventParameterExtendedParameters, _context=2)


class EventParameterFloatingLimit(Sequence):
    _order = (
        "timeDelay",
        "setpointReference",
        "lowDiffLimit",
        "highDiffLimit",
        "deadband",
    )
    timeDelay = Unsigned(_context=0)
    setpointReference = DeviceObjectPropertyReference(_context=1)
    lowDiffLimit = Real(_context=2)
    highDiffLimit = Real(_context=3)
    deadband = Real(_context=4)


class EventParameterOutOfRange(Sequence):
    _order = ("timeDelay", "lowLimit", "highLimit", "deadband")
    timeDelay = Unsigned(_context=0)
    lowLimit = Real(_context=1)
    highLimit = Real(_context=2)
    deadband = Real(_context=3)


class EventParameterSignedOutOfRange(Sequence):
    _order = ("timeDelay", "lowLimit", "highLimit", "deadband")
    timeDelay = Unsigned(_context=0)
    lowLimit = Integer(_context=1)
    highLimit = Integer(_context=2)
    deadband = Unsigned(_context=3)


class EventParameterUnsignedOutOfRange(Sequence):
    _order = ("timeDelay", "lowLimit", "highLimit", "deadband")
    timeDelay = Unsigned(_context=0)
    lowLimit = Unsigned(_context=1)
    highLimit = Unsigned(_context=2)
    deadband = Unsigned(_context=3)


class EventParameterUnsignedRange(Sequence):
    _order = ("timeDelay", "lowLimit", "highLimit")
    timeDelay = Unsigned(_context=0)
    lowLimit = Unsigned(_context=1)
    highLimit = Unsigned(_context=2)


class FDTEntry(Sequence):
    _order = ("bacnetIPAddress", "timeToLive", "remainingTimeToLive")
    bacnetIPAddress = IPOctetString()
    timeToLive = Unsigned16()
    remainingTimeToLive = Unsigned16()


class ListOfFDTEntry(ListOf(FDTEntry)):
    pass


class FaultParameterCharacterString(Sequence):
    _order = ("listOfFaultValues",)
    listOfFaultValues = SequenceOf(CharacterString, _context=0)


class FaultParameterExtendedParameters(Choice):
    null = Null()
    real = Real()
    unsigned = Unsigned()
    boolean = Boolean()
    integer = Integer()
    double = Double()
    octet = OctetString()
    characterString = CharacterString()
    bitstring = BitString()
    enum = Enumerated()
    date = Date()
    time = Time()
    objectIdentifier = ObjectIdentifier()
    reference = DeviceObjectPropertyReference(_context=0)


class SequenceOfFaultParameterExtendedParameters(
    SequenceOf(FaultParameterExtendedParameters)
):
    pass


class FaultParameterExtended(Sequence):
    _order = ("vendorId", "extendedFaultType", "parameters")
    vendorId = Unsigned(_context=0)
    extendedFaultType = Unsigned(_context=1)
    parameters = SequenceOf(FaultParameterExtendedParameters, _context=2)


class FaultParameterLifeSafety(Sequence):
    _order = ("listOfFaultValues", "modePropertyReference")
    listOfFaultValues = SequenceOf(LifeSafetyState, _context=0)
    modePropertyReference = DeviceObjectPropertyReference(_context=1)


class FaultParameterState(Sequence):
    _order = ("listOfFaultValues",)
    listOfFaultValues = SequenceOf(PropertyStates, _context=0)


class FaultParameterStatusFlags(Sequence):
    _order = ("statusFlagsReference",)
    statusFlagsReference = DeviceObjectPropertyReference(_context=0)


class GetAlarmSummaryAlarmSummary(Sequence):
    _order = ("objectIdentifier", "alarmState", "acknowledgedTransitions")
    objectIdentifier = ObjectIdentifier()
    alarmState = EventState()
    acknowledgedTransitions = EventTransitionBits()


class GetEnrollmentSummaryRequestPriorityFilterType(Sequence):
    _order = ("minPriority", "maxPriority")
    minPriority = Unsigned(_context=0)
    maxPriority = Unsigned(_context=1)


class GetEnrollmentSummaryEnrollmentSummary(Sequence):
    _order = (
        "objectIdentifier",
        "eventType",
        "eventState",
        "priority",
        "notificationClass",
    )
    objectIdentifier = ObjectIdentifier()
    eventType = EventType()
    eventState = EventState()
    priority = Unsigned()
    notificationClass = Unsigned(_optional=True)


class GetEventInformationEventSummary(Sequence):
    _order = (
        "objectIdentifier",
        "eventState",
        "acknowledgedTransitions",
        "eventTimeStamps",
        "notifyType",
        "eventEnable",
        "eventPriorities",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    eventState = EventState(_context=1)
    acknowledgedTransitions = EventTransitionBits(_context=2)
    eventTimeStamps = SequenceOf(TimeStamp, _context=3)
    notifyType = NotifyType(_context=4)
    eventEnable = EventTransitionBits(_context=5)
    eventPriorities = SequenceOf(Unsigned, _context=6)


class LightingCommand(Sequence):
    _order = (
        "operation",
        "targetLevel",
        "rampRate",
        "stepIncrement",
        "fadeTime",
        "priority",
    )
    operation = LightingOperation(_context=0)
    targetLevel = Real(_context=1, _optional=True)
    rampRate = Real(_context=2, _optional=True)
    stepIncrement = Real(_context=3, _optional=True)
    fadeTime = Unsigned(_context=4, _optional=True)
    priority = Unsigned(_context=5, _optional=True)


class ChannelValue(Choice):
    null = Null()
    real = Real()
    enumerated = Enumerated()
    unsigned = Unsigned()
    boolean = Boolean()
    integer = Integer()
    double = Double()
    time = Time()
    characterString = CharacterString()
    octetString = OctetString()
    bitString = BitString()
    date = Date()
    objectidentifier = ObjectIdentifier()
    lightingCommand = LightingCommand(_context=0)


class GroupChannelValue(Sequence):
    _order = ("channel", "overridingPriority", "value")
    channel = Unsigned(_context=0)
    overridingPriority = Unsigned(_context=1, _optional=True)
    value = ChannelValue()


class KeyIdentifier(Sequence):
    _order = ("algorithm", "keyId")
    algorithm = Unsigned(_context=0)
    keyId = Unsigned(_context=1)


class LandingCallStatusCommand(Choice):
    direction = LiftCarDirection(_context=1)
    destination = Unsigned8(_context=2)


class LandingCallStatus(Sequence):
    _order = ("floorNumber", "command", "floorText")
    floorNumber = Unsigned8(_context=0)
    command = LandingCallStatusCommand()
    floorText = CharacterString(_context=3, _optional=True)


class LandingDoorStatusLandingDoor(Sequence):
    _order = ("floorNumber", "doorStatus")
    floorNumber = Unsigned8(_context=0)
    doorStatus = DoorStatus(_context=1)


class LandingDoorStatus(Sequence):
    _order = ("landingDoors",)
    landingDoors = SequenceOf(LandingDoorStatusLandingDoor, _context=0)


class LiftCarCallList(Sequence):
    _order = ("floorNumbers",)
    floorNumbers = SequenceOf(Unsigned8, _context=0)


class LogDataLogData(Choice):
    booleanValue = Boolean(_context=0)
    realValue = Real(_context=1)
    enumValue = Enumerated(_context=2)
    unsignedValue = Unsigned(_context=3)
    signedValue = Integer(_context=4)
    bitstringValue = BitString(_context=5)
    nullValue = Null(_context=6)
    failure = ErrorType(_context=7)
    anyValue = Any(_context=8)


class LogData(Choice):
    logStatus = LogStatus(_context=0)
    logData = SequenceOf(LogDataLogData, _context=1)
    timeChange = Real(_context=2)


class LogMultipleRecord(Sequence):
    _order = ("timestamp", "logData")
    timestamp = DateTime(_context=0)
    logData = LogData(_context=1)


class LogRecordLogDatum(Choice):
    logStatus = LogStatus(_context=0)
    booleanValue = Boolean(_context=1)
    realValue = Real(_context=2)
    enumValue = Enumerated(_context=3)
    unsignedValue = Unsigned(_context=4)
    signedValue = Integer(_context=5)
    bitstringValue = BitString(_context=6)
    nullValue = Null(_context=7)
    failure = ErrorType(_context=8)
    timeChange = Real(_context=9)
    anyValue = Any(_context=10)


class LogRecord(Sequence):
    _order = ("timestamp", "logDatum", "statusFlags")
    timestamp = DateTime(_context=0)
    logDatum = LogRecordLogDatum(_context=1)
    statusFlags = StatusFlags(_context=2, _optional=True)


@bacpypes_debugging
class AnyAtomicExtended(AnyAtomic):
    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return a valid value for the class."""
        if _debug:
            AnyAtomicExtended._debug("cast %r %r", cls, arg)
        # tag list is fine the way it is
        if isinstance(arg, TagList):
            return arg

        # make sure it is atomic
        if not isinstance(arg, (Atomic, DateTime)):
            raise TypeError("atomic or DateTime element expected")

        # let the argument encode itself
        tag_list = arg.encode()

        return tag_list

    def get_value_type(self) -> type:
        """Return the datatype encoded in the Any iff possible."""
        if len(self.tagList) == 1:
            if self.tagList[0].tag_class == TagClass.application:
                return Tag._app_tag_class[self.tagList[0].tag_number]
        elif len(self.tagList) == 2:
            if (
                (self.tagList[0].tag_class == TagClass.application)
                and (self.tagList[0].tag_number == TagNumber.date)
                and (self.tagList[1].tag_class == TagClass.application)
                and (self.tagList[1].tag_number == TagNumber.time)
            ):
                return DateTime

        raise TypeError("unable to determine encoded type")


@bacpypes_debugging
class NameValue(Sequence):
    _order = ("name", "value")
    name = CharacterString(_context=0)
    value = AnyAtomicExtended

    def encode(self) -> TagList:
        if _debug:
            NameValue._debug("(%r)encode", self.__class__.__name__)

        # start with a fresh tag list
        tag_list = TagList()

        # append the name
        name = self.name
        if name is None:
            raise MissingRequiredParameter(
                "name is a missing required element of %s" % (self.__class__.__name__,)
            )
        tag_list.extend(name.encode())

        # append the value
        if self.value is not None:
            tag_list.extend(self.value.encode())

        return tag_list

    @classmethod
    def decode(cls, tag_list: TagList) -> NameValue:
        """Decode an element from a tag list."""
        if _debug:
            NameValue._debug("(%r)decode %r", cls.__name__, tag_list)

        tag: Tag

        # look for the context encoded character string
        tag = tag_list.peek()
        if _debug:
            NameValue._debug("    - name tag: %r", tag)
        if (
            (tag is None)
            or (tag.tag_class != TagClass.context)
            or (tag.tag_number != 0)
        ):
            raise MissingRequiredParameter(
                "name is a missing required element of %s" % (cls.__name__,)
            )

        # pop it off and save the value
        tag_list.pop()
        tag = tag.context_to_app(TagNumber.characterString)
        name = tag.app_to_object()

        # look for the optional application encoded value
        tag = tag_list.peek()
        if _debug:
            NameValue._debug("    - value tag: %r", tag)

        value_tags = []
        if tag and (tag.tag_class == TagClass.application):
            # this is one of ours
            value_tags.append(tag_list.pop())

            # if it is a date check the next one for a time
            if tag.tag_number == TagNumber.date:
                next_tag = tag_list.peek()
                if _debug:
                    NameValue._debug("    - next_tag: %r", next_tag)

                if (
                    next_tag
                    and (next_tag.tag_class == TagClass.application)
                    and (next_tag.tag_number == TagNumber.time)
                ):
                    # this is the time part
                    value_tags.append(tag_list.pop())

        # build one and return it
        return cls(name=name, value=TagList(value_tags))


class NameValueCollection(Sequence):
    _order = ("members",)
    members = SequenceOf(NameValue, _context=0)


class NetworkSecurityPolicy(Sequence):
    _order = ("portId", "securityLevel")
    portId = Unsigned(_context=0)
    securityLevel = SecurityPolicy(_context=1)


class PortPermission(Sequence):
    _order = ("portId", "enabled")
    portId = Unsigned(_context=0)
    enabled = Boolean(_context=1)


class Prescale(Sequence):
    _order = ("multiplier", "moduloDivide")
    multiplier = Unsigned(_context=0)
    moduloDivide = Unsigned(_context=1)


class PropertyAccessResultAccessResult(Choice):
    propertyValue = Any(_context=4)
    propertyAccessError = ErrorType(_context=5)


class PropertyAccessResult(Sequence):
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "deviceIdentifier",
        "accessResult",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    deviceIdentifier = ObjectIdentifier(_context=3, _optional=True)
    accessResult = PropertyAccessResultAccessResult()


class RangeByPosition(Sequence):
    _order = ("referenceIndex", "count")
    referenceIndex = Unsigned()
    count = Integer()


class RangeBySequenceNumber(Sequence):
    _order = ("referenceSequenceNumber", "count")
    referenceSequenceNumber = Unsigned()
    count = Integer()


class RangeByTime(Sequence):
    _order = ("referenceTime", "count")
    referenceTime = DateTime()
    count = Integer()


class ReadAccessResultElementChoice(Choice):
    propertyValue = Any(_context=4)
    propertyAccessError = ErrorType(_context=5)


class ReadAccessResultElement(Sequence):
    _order = ("propertyIdentifier", "propertyArrayIndex", "readResult")
    propertyIdentifier = PropertyIdentifier(_context=2)
    propertyArrayIndex = Unsigned(_context=3, _optional=True)
    readResult = ReadAccessResultElementChoice()


class ReadAccessResult(Sequence):
    _order = ("objectIdentifier", "listOfResults")
    objectIdentifier = ObjectIdentifier(_context=0)
    listOfResults = SequenceOf(ReadAccessResultElement, _context=1)


class ReadAccessSpecification(Sequence):
    _order = ("objectIdentifier", "listOfPropertyReferences")
    objectIdentifier = ObjectIdentifier(_context=0)
    listOfPropertyReferences = SequenceOf(PropertyReference, _context=1)


class RouterEntry(Sequence):
    _order = ("networkNumber", "macAddress", "status")
    networkNumber = Unsigned16()
    macAddress = OctetString()
    status = RouterEntryStatus()


class SecurityKeySet(Sequence):
    _order = ("keyRevision", "activationTime", "expirationTime", "keyIds")
    keyRevision = Unsigned(_context=0)
    activationTime = DateTime(_context=1)
    expirationTime = DateTime(_context=2)
    keyIds = SequenceOf(KeyIdentifier, _context=3)


class SessionKey(Sequence):
    _order = ("sessionKey", "peerAddress")
    sessionKey = OctetString()
    peerAddress = Address()


class SetpointReference(Sequence):
    _order = ("setpointReference",)
    setpointReference = ObjectPropertyReference(_context=0, _optional=True)


class WeekNDay(OctetString(_length=3)):
    def __str__(self) -> str:
        if len(self) != 3:
            return "WeekNDay(?): " + repr(self)
        else:
            return "WeekNDay(%d, %d, %d)" % (self[0], self[1], self[2])


class CalendarEntry(Choice):
    date = Date(_context=0)
    dateRange = DateRange(_context=1)
    weekNDay = WeekNDay(_context=2)


class SpecialEventPeriod(Choice):
    calendarEntry = CalendarEntry(_context=0)
    calendarReference = ObjectIdentifier(_context=1)


class SpecialEvent(Sequence):
    _order = ("period", "listOfTimeValues", "eventPriority")
    period = SpecialEventPeriod()
    listOfTimeValues = SequenceOf(TimeValue, _context=2)
    eventPriority = Unsigned(_context=3)


class StageLimitValue(Sequence):
    _order = ("limit", "values", "deadband")
    limit = Real()
    values = BitString()
    deadband = Real()


class VMACEntry(Sequence):
    _order = ("virtualMACAddress", "nativeMACAddress")
    virtualMACAddress = OctetString()
    nativeMACAddress = OctetString()


class VTSession(Sequence):
    _order = ("localVtSessionID", "remoteVtSessionID", "remoteVtAddress")
    localVtSessionID = Unsigned()
    remoteVtSessionID = Unsigned()
    remoteVtAddress = DeviceAddress()


class WhoHasLimits(Sequence):
    _order = ("deviceInstanceRangeLowLimit", "deviceInstanceRangeHighLimit")
    deviceInstanceRangeLowLimit = Unsigned(_context=0)
    deviceInstanceRangeHighLimit = Unsigned(_context=1)


class WriteAccessSpecification(Sequence):
    _order = ("objectIdentifier", "listOfProperties")
    objectIdentifier = ObjectIdentifier(_context=0)
    listOfProperties = SequenceOf(PropertyValue, _context=1)


class AtomicReadFileACKAccessMethodChoice(Choice):
    streamAccess = AtomicReadFileACKAccessMethodStreamAccess(_context=0)
    recordAccess = AtomicReadFileACKAccessMethodRecordAccess(_context=1)


class AtomicReadFileRequestAccessMethodChoice(Choice):
    streamAccess = AtomicReadFileRequestAccessMethodChoiceStreamAccess(_context=0)
    recordAccess = AtomicReadFileRequestAccessMethodChoiceRecordAccess(_context=1)


class AtomicWriteFileRequestAccessMethodChoice(Choice):
    streamAccess = AtomicWriteFileRequestAccessMethodChoiceStreamAccess(_context=0)
    recordAccess = AtomicWriteFileRequestAccessMethodChoiceRecordAccess(_context=1)


class AuditLogQueryParameters(Choice):
    byTarget = AuditLogQueryParametersByTarget(_context=0)
    bySource = AuditLogQueryParametersBySource(_context=1)


class ClientCOV(Choice):
    realIncrement = Real()
    defaultIncrement = Null()


class ConfirmedTextMessageRequestMessageClass(Choice):
    numeric = Unsigned(_context=0)
    character = CharacterString(_context=1)


class CreateObjectRequestObjectSpecifier(Choice):
    objectType = ObjectType(_context=0)
    objectIdentifier = ObjectIdentifier(_context=1)


class EventParameter(Choice):
    changeOfBitstring = EventParameterChangeOfBitstring(_context=0)
    changeOfState = EventParameterChangeOfState(_context=1)
    changeOfValue = EventParameterChangeOfValue(_context=2)
    commandFailure = EventParameterCommandFailure(_context=3)
    floatingLimit = EventParameterFloatingLimit(_context=4)
    outOfRange = EventParameterOutOfRange(_context=5)
    changeOfLifesafety = EventParameterChangeOfLifeSafety(_context=8)
    extended = EventParameterExtended(_context=9)
    bufferReady = EventParameterBufferReady(_context=10)
    unsignedRange = EventParameterUnsignedRange(_context=11)
    accessEvent = EventParameterAccessEvent(_context=13)
    doubleOutOfRange = EventParameterDoubleOutOfRange(_context=14)
    signedOutOfRange = EventParameterSignedOutOfRange(_context=15)
    unsignedOutOfRange = EventParameterUnsignedOutOfRange(_context=16)
    changeOfCharacterstring = EventParameterChangeOfCharacterString(_context=17)
    changeOfStatusflags = EventParameterChangeOfStatusFlags(_context=18)


class FaultParameter(Choice):
    none = Null(_context=0)
    faultCharacterString = FaultParameterCharacterString(_context=1)
    faultExtended = FaultParameterExtended(_context=2)
    faultLifeSafety = FaultParameterLifeSafety(_context=3)
    faultState = FaultParameterState(_context=4)
    faultStatusFlags = FaultParameterStatusFlags(_context=5)


class ObjectSelector(Choice):
    none = Null()
    object = ObjectIdentifier()
    objectType = ObjectType()


class OptionalBinaryPV(Choice):
    null = Null()
    binaryPV = BinaryPV()


class OptionalCharacterString(Choice):
    null = Null()
    characterString = CharacterString()


class OptionalPriorityFilter(Choice):
    null = Null()
    filter = PriorityFilter()


class OptionalReal(Choice):
    null = Null()
    real = Real()


class OptionalUnsigned(Choice):
    null = Null()
    unsigned = Unsigned()


@bacpypes_debugging
class PriorityValue(Choice):
    null = Null()
    real = Real()
    enumerated = Enumerated()
    unsigned = Unsigned()
    boolean = Boolean()
    integer = Integer()
    double = Double()
    time = Time()
    characterString = CharacterString()
    octetString = OctetString()
    bitString = BitString()
    date = Date()
    objectidentifier = ObjectIdentifier()
    constructedValue = Any(_context=0)
    datetime = DateTime(_context=1)

    def __init__(
        self,
        arg: _Any = None,
        **kwargs,
    ) -> None:
        if _debug:
            PriorityValue._debug("__init__ %r %r", arg, kwargs)

        if arg is None:
            pass
        elif isinstance(arg, Null):
            kwargs["null"] = arg
        elif isinstance(arg, Real):
            kwargs["real"] = arg
        elif isinstance(arg, Enumerated):
            kwargs["enumerated"] = arg
        elif isinstance(arg, Unsigned):
            kwargs["unsigned"] = arg
        elif isinstance(arg, Boolean):
            kwargs["boolean"] = arg
        elif isinstance(arg, Integer):
            kwargs["integer"] = arg
        elif isinstance(arg, Double):
            kwargs["double"] = arg
        elif isinstance(arg, Time):
            kwargs["time"] = arg
        elif isinstance(arg, CharacterString):
            kwargs["characterString"] = arg
        elif isinstance(arg, OctetString):
            kwargs["octetString"] = arg
        elif isinstance(arg, BitString):
            kwargs["bitString"] = arg
        elif isinstance(arg, Date):
            kwargs["date"] = arg
        elif isinstance(arg, ObjectIdentifier):
            kwargs["objectIdentifier"] = arg
        elif isinstance(arg, DateTime):
            kwargs["datetime"] = arg
        elif isinstance(arg, Sequence):
            kwargs["constructedValue"] = arg
        else:
            raise TypeError(type(arg))

        super().__init__(**kwargs)


class PriorityArray(
    ArrayOf(
        PriorityValue,
        _length=16,
        _prototype=PriorityValue(null=()),
    )
):
    pass


class ProcessIdSelection(Choice):
    processIdentifier = Unsigned()
    nullValue = Null()


class Range(Choice):
    byPosition = RangeByPosition(_context=3)
    bySequenceNumber = RangeBySequenceNumber(_context=6)
    byTime = RangeByTime(_context=7)


class Scale(Choice):
    floatScale = Real(_context=0)
    integerScale = Integer(_context=1)


class ShedLevel(Choice):
    percent = Unsigned(_context=0)
    level = Unsigned(_context=1)
    amount = Real(_context=2)


class TimerStateChangeValue(Choice):
    null = Null()
    boolean = Boolean()
    unsigned = Unsigned()
    integer = Integer()
    real = Real()
    double = Double()
    octetstring = OctetString()
    characterstring = CharacterString()
    bitstring = BitString()
    enumerated = Enumerated()
    date = Date()
    time = Time()
    objectidentifier = ObjectIdentifier()
    noValue = Null(_context=0)
    constructedValue = Any(_context=1)
    datetime = DateTime(_context=2)
    lightingCommand = LightingCommand(_context=3)


class UnconfirmedTextMessageRequestMessageClass(Choice):
    numeric = Unsigned(_context=0)
    character = CharacterString(_context=1)


class ValueSource(Choice):
    none = Null(_context=0)
    object = DeviceObjectReference(_context=1)
    address = Address(_context=2)


class WhoHasObject(Choice):
    objectIdentifier = ObjectIdentifier(_context=2)
    objectName = CharacterString(_context=3)
