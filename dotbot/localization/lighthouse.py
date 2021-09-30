import numpy as np

periods = [959000, 957000];
# data = csvread('rc_car_drive/camera_lh2_test_8.csv',1);

def decode_packet(counts, polys, locations):
    c1A, c1B, c2A, c2B = [0] * 4

    # error check
    error_check = 0
    for j in range(4):
        if (polys[j]==0) or (polys[j]==1):
            error_check = error_check+1
        elif (polys[j]==2) or (polys[j]==3):
            error_check = error_check-1

    if error_check == 0:
        counts = np.sort(counts)
        sort_indices = np.argsort(counts)
        polys = polys[sort_indices]

        for j in range(4):
            if (polys[j]==0) or (polys[j]==1):
                if c1A == 0:
                    c1A = counts[j]
                else:
                    c2A = counts[j]
            elif (polys[j]==2) or (polys[j]==3):
                if c1B == 0:
                    c1B = counts[j]
                else:
                    c2B = counts[j]
    else:
        c1A = 99999999
        c2A = 99999999
        c1B = 99999999
        c2B = 99999999

    # bad_indexes = find(c1A==99999999);
    # c1A(bad_indexes) = []
    # c2A(bad_indexes) = []
    # c1B(bad_indexes) = []
    # c2B(bad_indexes) = []

    #  get rid of remaining points where c1 and c2 and very close
    # bad_indexes = [];
    # for i = 1:length(c1A)
    #     if (abs(c2A(i) - c1A(i)) < 1000)
    #         bad_indexes = [bad_indexes i];
    #     end
    #     if (abs(c2B(i) - c1B(i)) < 1000)
    #         bad_indexes = [bad_indexes i];

    # remove outliers
    # bad_indexes = [];
    # for i = 2:length(c1A)
    #     if (abs(c1A(i) - c1A(i-1)) > 5000):
    #         bad_indexes = [bad_indexes i]
    #     elif (abs(c2A(i) - c2A(i-1)) > 5000):
    #         bad_indexes = [bad_indexes i]
    #     elif (abs(c1B(i) - c1B(i-1)) > 5000):
    #         bad_indexes = [bad_indexes i]
    #     elif (abs(c2B(i) - c2B(i-1)) > 5000):
    #         bad_indexes = [bad_indexes i]

    # c1A(bad_indexes) = [];
    # c2A(bad_indexes) = [];
    # c1B(bad_indexes) = [];
    # c2B(bad_indexes) = [];

    a1A = (c1A*8/periods[0])*2*np.pi
    a2A = (c2A*8/periods[0])*2*np.pi
    a1B = (c1B*8/periods[1])*2*np.pi
    a2B = (c2B*8/periods[1])*2*np.pi

    azimuthA = 0.5*(a1A + a2A)
    azimuthB = 0.5*(a1B + a2B)

    elevationA = np.pi/2 - np.atan2(np.sin(a2A/2-a1A/2-60*np.pi/180), np.tan(np.pi/6))
    elevationB = np.pi/2 - np.atan2(np.sin(a2B/2-a1B/2-60*np.pi/180), np.tan(np.pi/6))

    return azimuthA, elevationA, azimuthB, elevationB